"""Клиент внутреннего API сайта программы ММКЯ (events.mibf.info).

Разведано 2026-09-06:
  GET /2026/api/locations        -> {"venues": {...}, "exhibitors": [...]}   (243 участника + 18 площадок)
  GET /2026/api/events           -> {"size": N, "refs": {...}, "events": [...]}  (кратко, без описаний)
  GET /2026/api/events/<id>      -> то же, но один event с description / participants / organizers / links
  GET /2026/api/events/search    -> {"term": ..., "search": [...]}

Особенность: без заголовка Referer с домена events.mibf.info API отдаёт
401 {"error":"Access Denied"}. Ключей/токенов не требуется.
"""
from __future__ import annotations

import time
from typing import Any

import requests

BASE = "https://events.mibf.info/2026"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class MibfApi:
    def __init__(self, base: str = BASE, timeout: int = 30, pause: float = 0.25):
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.pause = pause
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            # без Referer -> 401 Access Denied
            "Referer": f"{self.base}/program",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        })

    def _get(self, path: str, tries: int = 4) -> Any:
        url = f"{self.base}{path}"
        last = None
        for i in range(tries):
            try:
                r = self.s.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    time.sleep(self.pause)
                    return r.json()
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.RequestException as e:
                last = repr(e)
            time.sleep(2 * (i + 1))
        raise RuntimeError(f"{url} -> {last}")

    def locations(self) -> dict:
        """Площадки (полигоны на карте) и участники со стендами."""
        return self._get("/api/locations")

    def events(self) -> dict:
        """Полный список событий программы (без описаний)."""
        return self._get("/api/events")

    def event(self, event_id: str) -> dict:
        """Одно событие целиком: описание, спикеры, организаторы, ссылки."""
        return self._get(f"/api/events/{event_id}")
