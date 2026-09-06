"""Шаг 7. Выпуски программы «Библиотека» Радио РБК.

Событие ярмарки «Библиотека Радио РБК» (events.mibf.info/2026/program/Hv_ZYW)
ведёт на biblio.rbc.ru. Названия выпусков там не текстом, а картинками, и
плеер подставляет mp3 по номеру — из HTML список не собрать.

Рабочий путь: подкаст лежит на mave.digital, его RSS находится через
поиск Apple Podcasts (itunes.apple.com/search) и содержит все выпуски
с названиями, описаниями, датами и ссылками на аудио.

  -> data/rbc_biblio.json

Запуск:  python scripts/fetch_rbc_biblio.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
PODCAST = "Радио РБК Библиотека"
ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def get(url: str) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()


def find_feed(name: str) -> str:
    u = ("https://itunes.apple.com/search?entity=podcast&limit=15&country=RU&term="
         + urllib.parse.quote(name))
    data = json.loads(get(u))
    for r in data.get("results", []):
        if r.get("feedUrl"):
            print(f'подкаст: {r["collectionName"]} -> {r["feedUrl"]}')
            return r["feedUrl"]
    raise SystemExit(f"RSS для «{name}» не нашёлся в Apple Podcasts")


def text(el, *paths: str) -> str:
    for p in paths:
        got = el.find(p)
        if got is not None and (got.text or "").strip():
            return (got.text or "").strip()
    return ""


def main() -> None:
    feed = find_feed(PODCAST)
    root = ET.fromstring(get(feed))
    ch = root.find("channel")

    episodes = []
    for item in ch.findall("item"):
        enc = item.find("enclosure")
        desc = text(item, "description", f"{ITUNES_NS}summary")
        episodes.append({
            "title": text(item, "title"),
            "date": text(item, "pubDate"),
            "duration": text(item, f"{ITUNES_NS}duration"),
            "page": text(item, "link"),
            "audio": enc.get("url") if enc is not None else "",
            "description": re.sub(r"<[^>]+>", " ", desc).strip(),
        })

    out = {
        "podcast": text(ch, "title"),
        "site": text(ch, "link"),
        "feed": feed,
        "about": re.sub(r"<[^>]+>", " ", text(ch, "description")).strip(),
        "count": len(episodes),
        "episodes": episodes,
    }
    path = ROOT / "data" / "rbc_biblio.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Готово: {len(episodes)} выпусков -> {path}")
    for e in episodes[:5]:
        print(f'  {e["date"][:16]} · {e["title"][:80]}')


if __name__ == "__main__":
    main()
