"""Шаг 3b. Лекции и выступления спикеров на YouTube — через поисковую выдачу.

Один платный запрос XMLRiver на человека: ищем ролики на youtube.com,
отбрасываем каналы и плейлисты, оставляем конкретные видео.

  -> data/people_youtube.json  (resume)

Запуск:  python scripts/enrich_youtube.py --limit 1200
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

VIDEO = re.compile(r"^https?://(?:www\.)?youtube\.com/watch\?v=|^https?://youtu\.be/", re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200, help="сколько людей обработать")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    people = json.loads((ROOT / "data" / "people.json").read_text(encoding="utf-8"))["people"]
    out_path = ROOT / "data" / "people_youtube.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    targets = [p for p in people[: args.limit] if p["name"] not in done]
    print(f"людей к обработке: {len(targets)} (уже есть {len(done)}) — "
          f"{len(targets)} платных запросов XMLRiver")
    if not targets:
        return

    x = XmlRiver("google")
    queries = {f'site:youtube.com "{p["name"]}" лекция ИЛИ выступление ИЛИ интервью': p
               for p in targets}
    try:
        res = x.search_many(queries.keys(), workers=args.workers)
    except QuotaExhausted as e:
        print(f"XMLRiver: лимиты исчерпаны ({e}). Сохраняю что есть.")
        res = {}

    for q, docs in res.items():
        p = queries[q]
        vids, seen = [], set()
        for d in docs:
            if not VIDEO.match(d["url"]) or d["url"] in seen:
                continue
            seen.add(d["url"])
            vids.append({"url": d["url"], "title": d["title"], "snippet": d["snippet"][:200]})
        done[p["name"]] = {"name": p["name"], "videos": vids[:6]}

    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    withvid = sum(1 for v in done.values() if v["videos"])
    print(f"Готово: {len(done)} человек, у {withvid} нашлись ролики -> {out_path}")


if __name__ == "__main__":
    main()
