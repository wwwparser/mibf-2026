"""Шаг 10a. Разбор телеграм-адресов участников: что канал, а что личный профиль.

Ничего не меняет в аккаунте — только резолвит юзернеймы и складывает справку.
Нужен перед подпиской: на пользователя подписаться нельзя, а среди персональных
ссылок спикеров (их находил поиск) заметная часть — именно личные профили,
плюс возможны однофамильцы.

Источники:
  data/tg_channels.json    — каналы компаний, найденные на сайтах участников
  data/people_social.json  — телеграм-ссылки спикеров из поисковой выдачи

  -> data/tg_targets.json  (resume: уже проверенные не перезапрашиваются)

Запуск:  python scripts/tg_resolve_targets.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path.home() / ".claude" / "skills" / "telegram-chat-analysis"
sys.path.insert(0, str(SKILL))

from telethon import TelegramClient  # noqa: E402
from telethon.errors import FloodWaitError  # noqa: E402
from telethon.tl.types import Channel, Chat, User  # noqa: E402

import tg_common  # noqa: E402

OUT = ROOT / "data" / "tg_targets.json"
TG_USER = re.compile(r"t\.me/(?:s/)?([A-Za-z0-9_]{4,32})/?$")
# служебные адреса, которые ловятся регуляркой, но каналами не являются
BAD = {"share", "joinchat", "addstickers", "proxy", "iv", "telegram", "durov"}


def collect() -> dict[str, dict]:
    targets: dict[str, dict] = {}

    ch = json.loads((ROOT / "data" / "tg_channels.json").read_text(encoding="utf-8"))
    for c in ch["channels"]:
        if c["username"].lower() in BAD:
            continue
        targets[c["username"].lower()] = {
            "username": c["username"], "kind": "company",
            "who": c["exhibitor"], "group": c.get("group", ""),
        }

    soc = json.loads((ROOT / "data" / "people_social.json").read_text(encoding="utf-8"))
    for name, v in soc.items():
        for s in v.get("social", []):
            if s["network"] != "Telegram":
                continue
            m = TG_USER.search(s["url"])
            if not m or m.group(1).lower() in BAD:
                break
            key = m.group(1).lower()
            if key not in targets:                       # канал компании важнее
                targets[key] = {"username": m.group(1), "kind": "person",
                                "who": name, "group": ""}
            break
    return targets


async def run() -> None:
    targets = collect()
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [t for k, t in targets.items() if k not in done]
    print(f"адресов всего: {len(targets)}, проверить: {len(todo)}")

    api_id, api_hash = tg_common.api_credentials()
    session = str(Path.home() / ".claude" / "secrets" / "telegram")
    client = TelegramClient(session, int(api_id), api_hash, proxy=tg_common.proxy())
    await client.start()
    me = await client.get_me()
    print(f"Telegram OK: {me.first_name} (@{me.username})")

    for i, t in enumerate(todo, 1):
        key = t["username"].lower()
        rec = dict(t)
        try:
            ent = await client.get_entity(t["username"])
            if isinstance(ent, Channel):
                rec.update({
                    "type": "channel" if ent.broadcast else "group",
                    "title": ent.title,
                    "id": ent.id,
                    "participants": getattr(ent, "participants_count", None),
                    "joined": not ent.left if hasattr(ent, "left") else None,
                    "restricted": bool(getattr(ent, "restricted", False)),
                })
            elif isinstance(ent, Chat):
                rec.update({"type": "group", "title": ent.title, "id": ent.id})
            elif isinstance(ent, User):
                # на пользователя подписаться нельзя — только написать
                rec.update({"type": "user",
                            "title": " ".join(x for x in [ent.first_name, ent.last_name] if x),
                            "id": ent.id, "bot": bool(ent.bot)})
            else:
                rec.update({"type": "other"})
        except FloodWaitError as e:
            print(f"  ! FloodWait {e.seconds} c — останавливаюсь, сохраняю собранное")
            break
        except Exception as e:
            rec.update({"type": "error", "error": type(e).__name__})
        done[key] = rec
        if i % 20 == 0 or i == len(todo):
            OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {i}/{len(todo)}")
        await asyncio.sleep(1.0)                          # резолв тоже лимитируется

    OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    by_type = Counter(v.get("type") for v in done.values())
    joinable = [v for v in done.values() if v.get("type") in ("channel", "group")]
    already = [v for v in joinable if v.get("joined")]
    print(f"\nРазобрано: {len(done)}")
    for k, n in by_type.most_common():
        print(f"  {n:>4}  {k}")
    print(f"\nМожно подписаться: {len(joinable)} "
          f"(компаний {sum(1 for v in joinable if v['kind'] == 'company')}, "
          f"персональных {sum(1 for v in joinable if v['kind'] == 'person')})")
    print(f"Из них вы уже подписаны на: {len(already)}")
    print(f"-> {OUT}")
    await client.disconnect()


def main() -> None:
    os.environ.setdefault("TELEGRAM_PROXY", "")
    asyncio.run(run())


if __name__ == "__main__":
    main()
