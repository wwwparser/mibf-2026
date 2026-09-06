"""Шаг 1b. Карточки участников с карты ярмарки (events.mibf.info/2026/expo-map).

Список из /api/locations даёт только имя и номер стенда. Карточка по
/api/exhibitors/<id> отдаёт то, что показывает всплывающее окно на карте:
описание, сайт, почту, телефон, адрес, юрлицо. Это те же данные, что
организаторы публикуют на карте для посетителей.

  data/raw/exhibitors/<id>.json  — сырые карточки (resume)
  data/exhibitors.json           — обновляется на месте, к каждому участнику
                                   добавляются about / website / email / phone / зона

Запуск:  python scripts/fetch_exhibitors.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.mibf_api import MibfApi  # noqa: E402

RAW = ROOT / "data" / "raw" / "exhibitors"


def zone(stands: list) -> str:
    """Буква в номере стенда — сектор зала: A12 -> A."""
    for s in stands:
        m = re.match(r"([A-ZА-Я])", str(s).strip().upper())
        if m:
            return m.group(1)
    return "—"


def main() -> None:
    path = ROOT / "data" / "exhibitors.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["exhibitors"]
    RAW.mkdir(parents=True, exist_ok=True)

    api = MibfApi()
    todo = [x for x in items if not (RAW / f"{x['id']}.json").exists()]
    print(f"карточек скачать: {len(todo)} (уже есть {len(items) - len(todo)})")

    for i, x in enumerate(todo, 1):
        try:
            card = api._get(f"/api/exhibitors/{x['id']}")
            (RAW / f"{x['id']}.json").write_text(
                json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:
            print(f"  ! {x['id']} ({x['name']}): {exc}")
            continue
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}")

    filled = 0
    for x in items:
        p = RAW / f"{x['id']}.json"
        if not p.exists():
            continue
        card = json.loads(p.read_text(encoding="utf-8"))
        got = (card.get("exhibitors") or [None])[0]
        if not got:
            continue
        about = (got.get("about") or "").strip()
        if about.upper() in {"N/A", "-", "—"}:
            about = ""
        x.update({
            "about": about,
            "about_en": (got.get("about_en") or "").strip(),
            "website": (got.get("website") or "").strip(),
            "email": (got.get("email") or "").strip(),
            "phone": (got.get("phone") or "").strip(),
            "address": (got.get("address") or "").strip(),
            "legal_name": (got.get("legal_name") or "").strip(),
            "social": got.get("social"),
        })
        if about or x["website"] or x["email"]:
            filled += 1
        x["zone"] = zone(x["stands"])

    data["exhibitors"] = items
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    has = lambda k: sum(1 for x in items if x.get(k))  # noqa: E731
    print(f"\nГотово: {len(items)} участников, содержательных карточек {filled}")
    print(f"  описание: {has('about')} · сайт: {has('website')} · "
          f"почта: {has('email')} · телефон: {has('phone')}")


if __name__ == "__main__":
    main()
