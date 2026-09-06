"""XMLRiver — выдача Google/Яндекс в XML. Ключи из .env, никогда не в коде."""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

import requests

ROOT = Path(__file__).resolve().parents[2]

GOOGLE = "https://xmlriver.com/search/xml"
YANDEX = "https://xmlriver.com/search_yandex/xml"

# Москва: Google country=1011969, Яндекс lr=213
GEO = {"google": {"country": "2643", "lr": "ru", "loc": "1011969"}, "yandex": {"lr": "213", "lang": "ru"}}


def load_env(path: Path | None = None) -> None:
    p = path or ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


class XmlRiverError(RuntimeError):
    pass


class QuotaExhausted(XmlRiverError):
    """Кончились деньги/лимиты — долбить бесполезно, надо остановиться."""


class XmlRiver:
    def __init__(self, engine: str = "google", timeout: int = 90):
        load_env()
        self.user = os.getenv("XMLRIVER_USER")
        self.key = os.getenv("XMLRIVER_KEY")
        if not self.user or not self.key:
            raise RuntimeError(
                "Нет XMLRIVER_USER/XMLRIVER_KEY. Скопируйте их в .env "
                "(шаблон — .env.example, реальные ключи — ~/.claude/secrets/api-keys.env)."
            )
        self.engine = engine
        self.endpoint = GOOGLE if engine == "google" else YANDEX
        self.timeout = timeout
        self.s = requests.Session()

    def search(self, query: str, page: int | None = None, tries: int = 4) -> list[dict]:
        """Топ-10 выдачи. Один вызов = один платный запрос."""
        params = {"user": self.user, "key": self.key, "query": query, **GEO[self.engine]}
        if page is not None:
            params["page"] = str(page)
        last = ""
        for attempt in range(tries):
            try:
                r = self.s.get(self.endpoint, params=params, timeout=self.timeout)
                text = self._decode(r.content)
                root = ET.fromstring(text)
                err = root.find(".//error")
                if err is not None:
                    msg = (err.text or "").strip()
                    last = msg
                    low = msg.lower()
                    # «На вашем счету закончились деньги», «Превышено количество…» —
                    # ретраить бессмысленно, надо остановиться и сказать пользователю
                    if any(k in low for k in ("превышено", "баланс", "закончились деньги", "пополните")):
                        raise QuotaExhausted(msg)
                    # «Заняты все доступные каналы» — ждать дольше
                    time.sleep(15 if "канал" in msg else 4)
                    continue
                return self._parse(root)
            except (ET.ParseError, requests.RequestException) as e:
                last = repr(e)
                time.sleep(3 * (attempt + 1))
        raise XmlRiverError(f"{query!r}: {last}")

    @staticmethod
    def _decode(raw: bytes) -> str:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("windows-1251")

    @staticmethod
    def _parse(root: ET.Element) -> list[dict]:
        out = []
        for doc in root.iter("doc"):
            url = (doc.findtext("url") or "").strip()
            if not url:
                continue
            passages = " ".join((p.text or "") for p in doc.iter("passage")).strip()
            out.append({
                "url": url,
                "title": (doc.findtext("title") or "").strip(),
                "snippet": passages or (doc.findtext("headline") or "").strip(),
            })
        return out

    _dead = False

    def search_many(self, queries: Iterable[str], workers: int = 10) -> dict[str, list[dict]]:
        """Пул на 10 потоков — столько каналов даёт стандартный аккаунт."""
        queries = list(queries)
        res: dict[str, list[dict]] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for q, r in zip(queries, pool.map(self._safe, queries)):
                res[q] = r
        return res

    def _safe(self, q: str) -> list[dict]:
        try:
            return self.search(q)
        except QuotaExhausted:
            self._dead = True          # остальным воркерам уже незачем ходить
            raise
        except XmlRiverError:
            return []
