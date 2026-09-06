"""Шаг 2. Сквозной список книг, упомянутых на сайте ярмарки.

Источники: заголовки и описания всех 509 событий + текст пресс-релиза.
Метод: кандидаты вытаскиваются регуляркой по кавычкам-ёлочкам, затем DeepSeek
пакетами решает, что из этого действительно название книги, и приводит к
нормальной форме (книга / не книга, автор, если назван рядом).

  -> data/books.json

Запуск:  python scripts/extract_books.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.llm_client import chat_json  # noqa: E402

QUOTED = re.compile(r"«([^«»]{2,120})»")
TAG = re.compile(r"<[^>]+>")

SYSTEM = (
    "Ты фильтруешь список строк, найденных в кавычках в программе книжной ярмарки. "
    "Для каждой строки реши, является ли она НАЗВАНИЕМ КНИГИ (книга, сборник, роман, "
    "поэтический сборник, комикс, учебник). Названиями книг НЕ являются: издательства, "
    "премии, площадки, проекты, фестивали, серии, СМИ, компании, цитаты, лозунги. "
    'Ответ строго JSON: {"items":[{"raw":"...","is_book":true,"title":"нормализованное название","author":""}]}'
)


def clean(html: str) -> str:
    return TAG.sub(" ", html or "").replace("&nbsp;", " ")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="ограничить число кандидатов (для теста)")
    args = ap.parse_args()

    program = json.loads((ROOT / "data" / "program.json").read_text(encoding="utf-8"))
    press = (ROOT / "data" / "press" / "press-release.txt")
    press_text = press.read_text(encoding="utf-8") if press.exists() else ""

    # кандидат -> где встретился
    mentions: dict[str, list[dict]] = defaultdict(list)
    for e in program["events"]:
        blob = f"{e['title']} {clean(e['description'])}"
        for m in set(QUOTED.findall(blob)):
            mentions[m.strip()].append({"event_id": e["id"], "event_title": e["title"], "date": e["date"]})
    for m in set(QUOTED.findall(press_text)):
        mentions[m.strip()].append({"event_id": None, "event_title": "Пресс-релиз ММКЯ-2026", "date": None})

    cands = sorted(mentions, key=lambda x: (-len(mentions[x]), x.lower()))
    if args.limit:
        cands = cands[: args.limit]
    print(f"кандидатов в кавычках: {len(cands)}")

    books = []
    BATCH = 60
    for i in range(0, len(cands), BATCH):
        chunk = cands[i : i + BATCH]
        try:
            res = chat_json(SYSTEM, json.dumps({"strings": chunk}, ensure_ascii=False))
        except Exception as exc:
            print(f"  ! пакет {i}: {exc}")
            continue
        for it in res.get("items", []):
            if not it.get("is_book"):
                continue
            raw = it.get("raw") or ""
            books.append({
                "title": (it.get("title") or raw).strip(),
                "raw": raw,
                "author": (it.get("author") or "").strip(),
                "mentions": mentions.get(raw, []),
                "mention_count": len(mentions.get(raw, [])),
            })
        print(f"  {min(i + BATCH, len(cands))}/{len(cands)} -> книг всего {len(books)}")

    books.sort(key=lambda b: (-b["mention_count"], b["title"].lower()))
    out = ROOT / "data" / "books.json"
    out.write_text(json.dumps({"count": len(books), "books": books}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nГотово: {len(books)} книг -> {out}")


if __name__ == "__main__":
    main()
