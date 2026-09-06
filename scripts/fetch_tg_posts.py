"""Шаг 9. Посты телеграм-каналов участников за последние N дней.

Каналы берутся из data/tg_channels.json (их находит merge_contacts.py на сайтах
участников). Выгружаем только свежее окно — по умолчанию 10 дней, то есть
период ярмарки плюс несколько дней до и после.

Работает на общей сессии скилла telegram-chat-analysis
(~/.claude/secrets/telegram.session). MTProto из РФ обычно требует локального
SOCKS5 VPN-клиента (PROXY_LOCAL), но проверено 6 сентября 2026: с этой машины
подключение проходит и напрямую, поэтому прокси включается только если он задан.

  -> data/tg_posts.json  (resume: уже выгруженные каналы пропускаются)

Запуск:  python scripts/fetch_tg_posts.py --days 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path.home() / ".claude" / "skills" / "telegram-chat-analysis"
sys.path.insert(0, str(SKILL))

from telethon import TelegramClient  # noqa: E402
from telethon.errors import FloodWaitError  # noqa: E402

import tg_common  # noqa: E402


async def run(days: int, limit: int) -> None:
    channels = json.loads((ROOT / "data" / "tg_channels.json").read_text(encoding="utf-8"))["channels"]
    out_path = ROOT / "data" / "tg_posts.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    api_id, api_hash = tg_common.api_credentials()
    session = str(Path.home() / ".claude" / "secrets" / "telegram")

    client = TelegramClient(session, int(api_id), api_hash, proxy=tg_common.proxy())
    await client.start()
    me = await client.get_me()
    print(f"Telegram OK: {me.first_name} (@{me.username})")
    print(f"каналов: {len(channels)}, окно: с {since:%Y-%m-%d}")

    ok = fail = 0
    for i, ch in enumerate(channels, 1):
        name = ch["username"]
        if name in done:
            continue
        posts = []
        try:
            async for m in client.iter_messages(name, limit=limit):
                if m.date < since:
                    break
                text = (m.text or "").strip()
                if not text:
                    continue
                posts.append({
                    "id": m.id,
                    "date": m.date.isoformat(),
                    "views": getattr(m, "views", None),
                    "text": text,
                    "link": f"https://t.me/{name}/{m.id}",
                })
            done[name] = {**ch, "posts": posts, "post_count": len(posts)}
            ok += 1
        except FloodWaitError as e:
            print(f"  ! FloodWait {e.seconds} c — останавливаюсь, сохраняю собранное")
            break
        except Exception as e:                       # канал закрыт, переименован, не существует
            done[name] = {**ch, "posts": [], "post_count": 0, "error": type(e).__name__}
            fail += 1
        if i % 10 == 0 or i == len(channels):
            out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {i}/{len(channels)}  ok={ok} ошибок={fail}")
        await asyncio.sleep(0.6)                     # лимиты Telegram настоящие

    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(v["post_count"] for v in done.values())
    live = sum(1 for v in done.values() if v["post_count"])
    print(f"\nГотово: {len(done)} каналов, постов за {days} дней: {total} "
          f"(писали {live} каналов) -> {out_path}")
    await client.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--limit", type=int, default=300, help="потолок сообщений на канал")
    args = ap.parse_args()
    os.environ.setdefault("TELEGRAM_PROXY", "")      # напрямую, если прокси не задан явно
    asyncio.run(run(args.days, args.limit))


if __name__ == "__main__":
    main()
