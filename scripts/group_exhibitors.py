"""Шаг 1c. Группировка участников по типу организации.

Дешёвая модель раскладывает 243 участника по типам, опираясь на название
и описание с карты. Тип нужен, чтобы список участников читался: издательство,
зарубежный участник, библиотека и книжный магазин — это очень разные соседи
по стенду.

  -> data/exhibitors.json  (у каждого участника появляется поле group)

Запуск:  python scripts/group_exhibitors.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.llm_client import chat_json  # noqa: E402

GROUPS = [
    "Издательство",
    "Зарубежный участник",
    "Книжный магазин и дистрибуция",
    "Библиотека",
    "Государственная организация",
    "Образование и наука",
    "СМИ и медиа",
    "Цифровой сервис и технологии",
    "Общественная организация и фонд",
    "Прочее",
]

SYSTEM = (
    "Ты классифицируешь участников книжной ярмарки по типу организации. "
    f"Допустимые значения group строго из списка: {', '.join(GROUPS)}. "
    "«Зарубежный участник» ставь для национальных стендов и иностранных институций "
    "(Иран, Индия, Китай, ОАЭ, Беларусь и т.п.), даже если это издательство. "
    "Если по названию и описанию тип не определяется — «Прочее». "
    'Ответ строго JSON: {"items":[{"id":"...","group":"..."}]}'
)


def main() -> None:
    path = ROOT / "data" / "exhibitors.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["exhibitors"]

    todo = [x for x in items if not x.get("group")]
    print(f"классифицировать: {len(todo)} из {len(items)}")

    by_id = {x["id"]: x for x in items}
    BATCH = 25
    for i in range(0, len(todo), BATCH):
        chunk = [{
            "id": x["id"],
            "name": x["name"],
            "name_en": x.get("name_en", ""),
            "about": (x.get("about") or x.get("about_en") or "")[:300],
        } for x in todo[i: i + BATCH]]
        try:
            res = chat_json(SYSTEM, json.dumps({"exhibitors": chunk}, ensure_ascii=False))
        except Exception as exc:
            print(f"  ! пакет {i}: {exc}")
            continue
        for it in res.get("items", []):
            x = by_id.get(it.get("id"))
            if x and it.get("group") in GROUPS:
                x["group"] = it["group"]
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")

    for x in items:
        x.setdefault("group", "Прочее")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nГруппы:")
    for g, n in Counter(x["group"] for x in items).most_common():
        print(f"  {n:4}  {g}")


if __name__ == "__main__":
    main()
