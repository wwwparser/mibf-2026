"""Шаг 3. Соцсети спикеров и блогеров из программы — через XMLRiver.

Для каждого имени идёт один платный запрос в Google, из топ-10 выбираются
профили в соцсетях. Дорого при 1126 именах, поэтому по умолчанию берутся
только те, кто выступает чаще всего (--limit).

  -> data/people_social.json  (resume: уже найденные не перезапрашиваются)

Запуск:  python scripts/enrich_people.py --limit 40
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.xmlriver_client import QuotaExhausted, XmlRiver  # noqa: E402

# домен -> как называть в интерфейсе
SOCIAL = {
    "vk.com": "ВКонтакте", "t.me": "Telegram", "telegram.me": "Telegram",
    "ok.ru": "Одноклассники", "dzen.ru": "Дзен", "zen.yandex.ru": "Дзен",
    "youtube.com": "YouTube", "rutube.ru": "RuTube", "livejournal.com": "LiveJournal",
    "author.today": "Author.Today", "litres.ru": "Литрес", "ru.wikipedia.org": "Википедия",
}
BAD = re.compile(r"/(share|widget|search|away|video_ext)", re.I)


def host(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return (m.group(1) if m else "").lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="сколько самых частых спикеров обработать")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    people = json.loads((ROOT / "data" / "people.json").read_text(encoding="utf-8"))["people"]
    out_path = ROOT / "data" / "people_social.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    targets = [p for p in people[: args.limit] if p["name"] not in done]
    print(f"спикеров к обработке: {len(targets)} (уже есть {len(done)}) — {len(targets)} платных запросов XMLRiver")
    if not targets:
        return

    x = XmlRiver("google")
    queries = {f'{p["name"]} писатель ИЛИ автор ИЛИ блогер соцсети vk telegram': p for p in targets}
    try:
        res = x.search_many(queries.keys(), workers=args.workers)
    except QuotaExhausted as e:
        print(f"XMLRiver: лимиты исчерпаны ({e}). Останавливаюсь, сохраняю что есть.")
        res = {}

    for q, docs in res.items():
        p = queries[q]
        links, seen = [], set()
        for d in docs:
            h = host(d["url"])
            key = next((k for k in SOCIAL if h == k or h.endswith("." + k)), None)
            if not key or BAD.search(d["url"]) or d["url"] in seen:
                continue
            seen.add(d["url"])
            links.append({"network": SOCIAL[key], "url": d["url"], "title": d["title"]})
        done[p["name"]] = {
            "name": p["name"], "role": p.get("role", ""),
            "events": p["events"], "social": links,
            "web": [d for d in docs[:3] if host(d["url"]) not in SOCIAL],
        }

    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    found = sum(1 for v in done.values() if v["social"])
    print(f"Готово: {len(done)} спикеров, у {found} нашлись соцсети -> {out_path}")


if __name__ == "__main__":
    main()
