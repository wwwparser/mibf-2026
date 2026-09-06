"""Шаг 6 (опционально). Список видео сообщества ярмарки во ВКонтакте.

Страница vkvideo.ru/@mmkya отдаёт редирект и рендерится скриптами, поэтому
ролики берём методом video.get VK API. Нужен сервисный токен сообщества
или standalone-приложения: положите его в .env как VK_SERVICE_TOKEN.

  -> data/vk_videos.json

Запуск:  python scripts/fetch_vk_video.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.xmlriver_client import load_env  # noqa: E402

API = "https://api.vk.com/method"
VERSION = "5.199"
SCREEN_NAME = "mmkya"


def call(method: str, token: str, **params) -> dict:
    r = requests.get(f"{API}/{method}", params={**params, "access_token": token, "v": VERSION}, timeout=40)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"VK {method}: {data['error'].get('error_msg')}")
    return data["response"]


def main() -> None:
    load_env()
    token = os.getenv("VK_SERVICE_TOKEN")
    if not token:
        raise SystemExit(
            "Нет VK_SERVICE_TOKEN в .env.\n"
            "Взять его можно в настройках сообщества (Управление → Работа с API → Ключи доступа)\n"
            "или в standalone-приложении на dev.vk.com."
        )

    group = call("groups.getById", token, group_id=SCREEN_NAME)
    gid = (group["groups"][0] if isinstance(group, dict) and "groups" in group else group[0])["id"]
    owner = -gid
    print(f"сообщество {SCREEN_NAME} -> owner_id {owner}")

    videos, offset = [], 0
    while True:
        chunk = call("video.get", token, owner_id=owner, count=200, offset=offset)
        items = chunk.get("items", [])
        videos += items
        print(f"  получено {len(videos)} из {chunk.get('count')}")
        offset += len(items)
        if not items or offset >= chunk.get("count", 0):
            break
        time.sleep(0.4)

    out = [{
        "id": f'{v["owner_id"]}_{v["id"]}',
        "title": v.get("title"),
        "description": v.get("description"),
        "duration": v.get("duration"),
        "views": v.get("views"),
        "date": v.get("date"),
        "url": f'https://vkvideo.ru/video{v["owner_id"]}_{v["id"]}',
    } for v in videos]
    out.sort(key=lambda v: -(v["date"] or 0))

    path = ROOT / "data" / "vk_videos.json"
    path.write_text(json.dumps({"count": len(out), "videos": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Готово: {len(out)} роликов -> {path}")


if __name__ == "__main__":
    main()
