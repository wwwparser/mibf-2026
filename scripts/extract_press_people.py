"""Шаг 3a. Люди, названные в пресс-релизе, и слияние их со спикерами программы.

Пресс-релиз называет поимённо тех, кого нет в списках участников событий:
организаторов, чиновников, глав делегаций, авторов, о которых говорят
в третьем лице. Их вытаскивает дешёвая модель пакетами по страницам.

  -> data/people.json  (обновляется на месте: у людей из релиза появляется
                        источник "press" и цитата контекста)

Запуск:  python scripts/extract_press_people.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.llm_client import chat_json  # noqa: E402

SYSTEM = (
    "Ты извлекаешь имена людей из пресс-релиза книжной ярмарки. "
    "Верни всех названных поимённо физических лиц: писателей, поэтов, переводчиков, "
    "лекторов, экспертов, руководителей. Организации, издательства, названия книг, "
    "премий и площадок — НЕ люди. Имена классиков, о которых просто идёт речь "
    "(Пушкин, Толстой, Гоголь), помечай role='классик'. "
    'Ответ строго JSON: {"people":[{"name":"Имя Фамилия","role":"кем назван в тексте"}]}'
)


def main() -> None:
    txt_path = ROOT / "data" / "press" / "press-release.txt"
    if not txt_path.exists():
        raise SystemExit("Нет data/press/press-release.txt — сначала скачайте пресс-релиз.")
    text = re.sub(r"\s+", " ", txt_path.read_text(encoding="utf-8"))

    # режем по 4000 символов с нахлёстом, чтобы не рвать имя пополам
    CHUNK, OVER = 4000, 200
    chunks = [text[i: i + CHUNK] for i in range(0, len(text), CHUNK - OVER)]
    print(f"кусков текста: {len(chunks)}")

    found: dict[str, str] = {}
    for i, ch in enumerate(chunks, 1):
        try:
            res = chat_json(SYSTEM, ch)
        except Exception as exc:
            print(f"  ! кусок {i}: {exc}")
            continue
        for p in res.get("people", []):
            name = (p.get("name") or "").strip()
            if len(name.split()) < 2 or len(name) > 60:
                continue
            found.setdefault(name, (p.get("role") or "").strip())
        print(f"  {i}/{len(chunks)} -> людей всего {len(found)}")

    people_path = ROOT / "data" / "people.json"
    data = json.loads(people_path.read_text(encoding="utf-8"))
    by_name = {p["name"]: p for p in data["people"]}

    added = 0
    for name, role in found.items():
        if name in by_name:
            by_name[name]["in_press"] = True
            by_name[name]["press_role"] = role
            continue
        by_name[name] = {
            "name": name, "role": role, "events": [],
            "in_press": True, "press_role": role,
        }
        added += 1

    out = sorted(by_name.values(), key=lambda x: (-len(x["events"]), x["name"]))
    people_path.write_text(
        json.dumps({"count": len(out), "people": out}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\nГотово: в релизе {len(found)} имён, из них новых {added}. "
          f"Всего людей: {len(out)} -> {people_path}")


if __name__ == "__main__":
    main()
