"""Шаг 11. Сырьё под статьи по темам программы.

Программа размечена самой ярмаркой по темам («НОН-ФИКШН», «ПОЭЗИЯ», «КОМИКСЫ»
и так далее). Скрипт собирает по каждой теме всё, что о ней известно из данных,
и просит дешёвую модель выделить повторяющиеся сюжеты — это механическая работа
над текстом, а не написание статьи.

  -> data/topics/<slug>.json   цифры, события, спикеры, книги, организаторы
  -> data/topics/<slug>.md     то же в читаемом виде — по нему пишется статья

Запуск:  python scripts/topic_digest.py [--topic ПОЭЗИЯ] [--no-llm]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.llm_client import chat_json  # noqa: E402

OUT = ROOT / "data" / "topics"
QUOTED = re.compile(r"«([^«»]{2,120})»")

SYSTEM = (
    "Ты разбираешь программу книжной ярмарки по одной теме. На входе — список событий "
    "с описаниями. Выдели, что в этой теме повторяется из события в событие. "
    "Не пересказывай отдельные события, ищи общее. "
    'Ответ строго JSON: {"threads":[{"title":"короткое имя сюжета",'
    '"what":"1-2 предложения, о чём он","events":["id","id"]}],'
    '"tensions":["спорные вопросы или противоречия, которые в теме обсуждают"],'
    '"notable":["конкретные факты, цифры, имена, которые стоит проверить и упомянуть"]}'
)


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()


def slug(s: str) -> str:
    tbl = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
           "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
           "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
           "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
           "ю": "yu", "я": "ya"}
    s = "".join(tbl.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "topic"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="разобрать только одну тему")
    ap.add_argument("--no-llm", action="store_true", help="без выделения сюжетов моделью")
    args = ap.parse_args()

    program = json.loads((ROOT / "data" / "program.json").read_text(encoding="utf-8"))
    refs = program["refs"]
    books_links = json.loads((ROOT / "data" / "books_links.json").read_text(encoding="utf-8"))
    social = json.loads((ROOT / "data" / "people_social.json").read_text(encoding="utf-8"))
    vk = json.loads((ROOT / "data" / "vk_videos.json").read_text(encoding="utf-8"))
    rec = {v["event"]["id"]: v for v in vk["videos"] if v.get("event")}

    by_topic: dict[str, list] = {}
    for e in program["events"]:
        by_topic.setdefault(e["topic"]["title"] or "БЕЗ ТЕМЫ", []).append(e)

    OUT.mkdir(parents=True, exist_ok=True)
    order = sorted(by_topic.items(), key=lambda x: -len(x[1]))

    for topic, evs in order:
        if args.topic and topic != args.topic:
            continue

        days = Counter((refs.get(e["date"]) or {}).get("title", e["date"]) for e in evs)
        venues = Counter(e["venue"]["title"] or "—" for e in evs)
        genres = Counter(e["genre"]["title"] or "—" for e in evs)
        orgs = Counter(o for e in evs for o in e["organizers"])
        people = Counter(
            (p.get("title") if isinstance(p, dict) else str(p)) or ""
            for e in evs for p in e["participants"])
        people.pop("", None)

        books = Counter()
        for e in evs:
            for t in set(QUOTED.findall(e["title"] + " " + strip_tags(e["description"]))):
                if t.strip() in books_links:
                    books[t.strip()] += 1

        items = [{
            "id": e["id"], "title": e["title"], "date": e["date"],
            "venue": e["venue"]["title"], "genre": e["genre"]["title"],
            "organizers": e["organizers"],
            "people": [(p.get("title") if isinstance(p, dict) else str(p)) for p in e["participants"]],
            "desc": strip_tags(e["description"])[:600],
            "video": bool(rec.get(e["id"])),
        } for e in sorted(evs, key=lambda x: (x["date"] or "", x["start"] or ""))]

        data = {
            "topic": topic, "count": len(evs),
            "days": days.most_common(), "venues": venues.most_common(),
            "genres": genres.most_common(12), "organizers": orgs.most_common(15),
            "people": people.most_common(30), "books": books.most_common(25),
            "with_video": sum(1 for i in items if i["video"]),
            "events": items,
        }

        if not args.no_llm:
            payload = json.dumps({"topic": topic, "events": [
                {"id": i["id"], "title": i["title"], "desc": i["desc"][:320]} for i in items
            ][:70]}, ensure_ascii=False)
            try:
                data["llm"] = chat_json(SYSTEM, payload, max_tokens=6000)
            except Exception as exc:
                print(f"  ! {topic}: модель не ответила — {exc}")

        name = slug(topic)
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                         encoding="utf-8")

        md = [f"# {topic} — {len(evs)} событий\n",
              "## По дням\n" + "\n".join(f"- {d}: {n}" for d, n in data["days"]),
              "\n## Площадки\n" + "\n".join(f"- {v}: {n}" for v, n in data["venues"][:8]),
              "\n## Жанры\n" + "\n".join(f"- {g}: {n}" for g, n in data["genres"][:8]),
              "\n## Организаторы\n" + "\n".join(f"- {o}: {n}" for o, n in data["organizers"]),
              "\n## Кто выступал чаще всего\n" + "\n".join(
                  f"- {p} ({n})" + ("  [соцсети есть]" if social.get(p, {}).get("social") else "")
                  for p, n in data["people"][:25]),
              "\n## Книги, упомянутые в теме\n" + "\n".join(f"- «{b}» ({n})" for b, n in data["books"]),
              ]
        if data.get("llm"):
            lm = data["llm"]
            md.append("\n## Сюжеты (черновой разбор моделью)\n" + "\n".join(
                f"- **{t.get('title')}** — {t.get('what')}" for t in lm.get("threads", [])))
            md.append("\n## Спорные места\n" + "\n".join(f"- {x}" for x in lm.get("tensions", [])))
            md.append("\n## Что проверить\n" + "\n".join(f"- {x}" for x in lm.get("notable", [])))
        md.append("\n## Все события\n" + "\n\n".join(
            f"### {i['title']}\n`{i['id']}` · {i['date']} · {i['venue']} · {i['genre']}"
            + (" · есть запись" if i["video"] else "")
            + (f"\nОрганизаторы: {', '.join(i['organizers'])}" if i["organizers"] else "")
            + (f"\nУчастники: {', '.join(x for x in i['people'] if x)}" if i["people"] else "")
            + (f"\n{i['desc']}" if i["desc"] else "")
            for i in items))

        (OUT / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
        size = (OUT / f"{name}.md").stat().st_size
        print(f"{topic:<32} {len(evs):>4} событий · спикеров {len(people)} · "
              f"книг {len(books)} · записей {data['with_video']} -> {name}.md ({size // 1024} КБ)")


if __name__ == "__main__":
    main()
