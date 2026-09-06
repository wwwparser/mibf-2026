"""Шаг 1. Выкачивает всю фактуру ММКЯ-2026 в data/.

  data/raw/locations.json   — площадки + участники со стендами
  data/raw/events.json      — список всех событий (краткий)
  data/events/<id>.json     — карточка каждого события (resume: уже скачанные пропускаются)
  data/program.json         — нормализованная программа (то, из чего строится сайт)
  data/exhibitors.json      — нормализованный список участников

Запуск:  python scripts/fetch_all.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.mibf_api import MibfApi  # noqa: E402

RAW = ROOT / "data" / "raw"
EV = ROOT / "data" / "events"


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    api = MibfApi()

    print("locations...", end=" ", flush=True)
    loc = api.locations()
    dump(RAW / "locations.json", loc)
    exhibitors = [e for e in loc.get("exhibitors", []) if e.get("type") == "exhibitor"]
    venues_meta = [e for e in loc.get("exhibitors", []) if e.get("type") == "venue"]
    print(f"{len(exhibitors)} участников, {len(venues_meta)} площадок")

    print("events list...", end=" ", flush=True)
    lst = api.events()
    dump(RAW / "events.json", lst)
    refs = lst["refs"]
    events = lst["events"]
    print(f"{len(events)} событий")

    # карточки событий, с resume
    EV.mkdir(parents=True, exist_ok=True)
    todo = [e for e in events if not (EV / f"{e['id']}.json").exists()]
    print(f"карточек скачать: {len(todo)} (уже есть {len(events) - len(todo)})")
    for i, e in enumerate(todo, 1):
        try:
            one = api.event(e["id"])
            dump(EV / f"{e['id']}.json", one)
        except Exception as exc:  # не роняем весь прогон из-за одного события
            print(f"  ! {e['id']}: {exc}")
            continue
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}")

    # ---- нормализация ----
    full = {}
    for e in events:
        p = EV / f"{e['id']}.json"
        if not p.exists():
            full[e["id"]] = e
            continue
        card = json.loads(p.read_text(encoding="utf-8"))
        refs.update(card.get("refs", {}))
        full[e["id"]] = {**e, **(card["events"][0] if card.get("events") else {})}

    def ref(key):
        r = refs.get(key) or {}
        return {"id": key, "title": r.get("title"), "color": r.get("color"), "prefix": r.get("prefix")}

    program = {
        "source": "https://events.mibf.info/2026/api/events",
        "count": len(full),
        "dates": sorted({v["date"] for v in full.values() if v.get("date")}),
        "refs": refs,
        "events": [
            {
                "id": v["id"],
                "date": v.get("date"),
                "start": v.get("startTime"),
                "end": v.get("endTime"),
                "title": v.get("title"),
                "title_en": v.get("title_en"),
                "description": v.get("description") or "",
                "canceled": bool(v.get("canceled")),
                "venue": ref(v.get("venue")),
                "genre": ref(v.get("genre")),
                "topic": ref(v.get("topic")),
                "organizers": v.get("organizers") or [],
                "participants": v.get("participants") or [],
                "links": v.get("links") or [],
                "url": f"https://events.mibf.info/2026/program/{v['id']}?d={v.get('date')}",
            }
            for v in sorted(full.values(), key=lambda x: (x.get("date") or "", x.get("startTime") or ""))
        ],
    }
    dump(ROOT / "data" / "program.json", program)

    ex_out = []
    for e in exhibitors:
        stands = []
        for l in e.get("locations") or []:
            for s in l.get("stends") or []:
                if isinstance(s, list):
                    stands += [x for x in s if x]
                elif s:
                    stands.append(s)
        ex_out.append({
            "id": e["id"],
            "name": (e.get("name") or "").strip(),
            "name_en": (e.get("name_en") or "").strip(),
            "prefix": e.get("prefix") or "",
            "stands": stands,
            "is_group": bool(e.get("is_group")),
        })
    ex_out.sort(key=lambda x: x["name"].lower())
    dump(ROOT / "data" / "exhibitors.json", {"count": len(ex_out), "exhibitors": ex_out})

    # сводка по людям (спикеры) — вход для обогащения соцсетями
    people = {}
    for v in program["events"]:
        for p in v["participants"]:
            title = (p.get("title") if isinstance(p, dict) else str(p)) or ""
            title = title.strip()
            if not title:
                continue
            slot = people.setdefault(title, {"name": title, "role": (p.get("subtitle") if isinstance(p, dict) else "") or "", "events": []})
            slot["events"].append(v["id"])
    dump(ROOT / "data" / "people.json", {"count": len(people), "people": sorted(people.values(), key=lambda x: -len(x["events"]))})

    print(f"\nГотово: {len(program['events'])} событий, {len(ex_out)} участников, {len(people)} спикеров")
    print("  data/program.json, data/exhibitors.json, data/people.json")


if __name__ == "__main__":
    main()
