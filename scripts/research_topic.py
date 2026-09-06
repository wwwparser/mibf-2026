"""Шаг 8. Сбор фактуры под статью: поисковая выдача + ролики на YouTube.

Скрипт не пишет текст — он собирает сырьё, по которому статья пишется дальше
вручную. На каждую тему уходит несколько платных запросов XMLRiver.

  -> data/research/<slug>.json

Запуск:
  python scripts/research_topic.py "КНИГАБАЙТ" --queries "КНИГАБАЙТ сервис" "КНИГАБАЙТ ИИ редактура"
  python scripts/research_topic.py --preset services
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

OUT = ROOT / "data" / "research"

# темы, которые всплыли в программе ярмарки и просят отдельного разбора
PRESETS = {
    "services": {
        "КНИГАБАЙТ": [
            "КНИГАБАЙТ издательский сервис",
            "КНИГАБАЙТ искусственный интеллект редактура рукописи",
            "КНИГАБАЙТ Наумов Лев",
        ],
        "RUGRAM": [
            "RUGRAM издательство self-publishing",
            "RUGRAM print on demand как издать книгу",
            "RUGRAM Давыдов Денис",
        ],
        "IBIS": [
            "IBIS книжный сервис издательский",
            "IBIS издательская система ИИ книги",
        ],
        "ИИ-редактура рукописей": [
            "ИИ редактура рукописи сервис для авторов 2026",
            "нейросеть редактор книги авторский голос",
        ],
    },
}

YT = re.compile(r"^https?://(?:www\.)?youtube\.com/watch\?v=|^https?://youtu\.be/", re.I)


def slug(s: str) -> str:
    tbl = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
           "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
           "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
           "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
           "ю": "yu", "я": "ya"}
    s = "".join(tbl.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "topic"


def research(topic: str, queries: list[str], x: XmlRiver) -> dict:
    qs = list(queries) + [f'site:youtube.com "{topic}"']
    try:
        res = x.search_many(qs)
    except QuotaExhausted as e:
        print(f"  XMLRiver: {e}")
        return {}

    web, videos, seen = [], [], set()
    for q, docs in res.items():
        for d in docs:
            if d["url"] in seen:
                continue
            seen.add(d["url"])
            (videos if YT.match(d["url"]) else web).append({**d, "query": q})

    data = {"topic": topic, "queries": qs, "web": web[:30], "videos": videos[:12]}
    path = OUT / f"{slug(topic)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {topic}: {len(web)} страниц, {len(videos)} роликов -> {path.name}")
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic", nargs="?", help="тема (если не задан --preset)")
    ap.add_argument("--queries", nargs="*", default=[])
    ap.add_argument("--preset", choices=sorted(PRESETS))
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    x = XmlRiver("google")

    if args.preset:
        for topic, queries in PRESETS[args.preset].items():
            research(topic, queries, x)
        return
    if not args.topic:
        raise SystemExit("Укажите тему или --preset")
    research(args.topic, args.queries or [args.topic], x)


if __name__ == "__main__":
    main()
