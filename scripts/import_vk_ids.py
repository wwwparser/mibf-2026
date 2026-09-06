"""Шаг 6c. Проставляет роликам VK их настоящие id — без них не собрать плеер.

VK не отдаёт список видео сообщества без авторизации, поэтому id снимаются
из живого браузера пользователя скиллом browser-bridge:

    python ~/.claude/skills/browser-bridge/bridge.py serve        # в фоне
    # включить мост в попапе расширения, затем:
    python ~/.claude/skills/browser-bridge/bridge.py pin "https://vkvideo.ru/@mmkya/all"
    python ~/.claude/skills/browser-bridge/bridge.py eval '<сборщик из README>' > ids.json

Формат входа — JSON-массив или строки «video-98267658_456241289|50:13|Название»:
длительность или название нужны, чтобы сопоставить id с роликом из списка.

  -> data/vk_videos.json  (у сопоставленных роликов появляется vk_id и embed)

Запуск:  python scripts/import_vk_ids.py ids.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO = re.compile(r"video(-?\d+)_(\d+)")


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\.(mp4|mov)$", "", s)
    return re.sub(r"[^a-zа-я0-9 ]+", " ", s).strip()


def parse(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8").strip()
    out = []
    if raw.startswith("{") or raw.startswith("["):
        data = json.loads(raw)
        items = data.get("items", data) if isinstance(data, dict) else data
        if isinstance(items, dict):                     # {"video-1_2": {...}}
            items = [{"id": k, **v} for k, v in items.items()]
        for it in items:
            m = VIDEO.search(it.get("id") or it.get("url") or "")
            if m:
                out.append({"oid": m.group(1), "vid": m.group(2),
                            "title": it.get("title", ""), "duration": it.get("duration", "")})
        return out
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("|")]
        m = VIDEO.search(parts[0] if parts else "")
        if not m:
            continue
        rest = parts[1:] + ["", ""]
        dur = rest[0] if re.match(r"^\d+:\d", rest[0]) else ""
        title = rest[1] if dur else rest[0]
        out.append({"oid": m.group(1), "vid": m.group(2), "title": title, "duration": dur})
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Укажите файл с id роликов (см. docstring)")
    ids = parse(Path(sys.argv[1]))
    print(f"id на входе: {len(ids)}")

    path = ROOT / "data" / "vk_videos.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    videos = data["videos"]

    # длительность годится как ключ, только если она уникальна:
    # у «Буктрейлера» и «Автор — нейросеть!» одинаковые 50:13
    dur_count = Counter(v.get("duration") for v in videos if v.get("duration"))

    matched = skipped = 0
    for rec in ids:
        best, score = None, 0.0
        if rec["duration"] and dur_count.get(rec["duration"]) == 1:
            best = next((v for v in videos
                         if v.get("duration") == rec["duration"] and not v.get("vk_id")), None)
            score = 1.0 if best else 0.0
        if not best and rec["title"]:
            for v in videos:
                if v.get("vk_id"):
                    continue
                r = SequenceMatcher(None, norm(rec["title"]), norm(v["title"])).ratio()
                if r > score:
                    best, score = v, r
        if not best or score < 0.72:
            skipped += 1
            print(f'  ? не сопоставлен: video{rec["oid"]}_{rec["vid"]} '
                  f'({rec["duration"] or rec["title"][:40] or "без подписи"})')
            continue
        best["vk_id"] = f'video{rec["oid"]}_{rec["vid"]}'
        best["url"] = f'https://vkvideo.ru/video{rec["oid"]}_{rec["vid"]}'
        best["embed"] = (f'https://vk.com/video_ext.php?oid={rec["oid"]}'
                         f'&id={rec["vid"]}&hd=2')
        matched += 1

    data["with_id"] = sum(1 for v in videos if v.get("vk_id"))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Сопоставлено: {matched}, пропущено как неоднозначные: {skipped}. "
          f"Всего роликов с id: {data['with_id']} из {len(videos)}")
    for v in videos:
        if v.get("vk_id"):
            print(f'  {v["vk_id"]}  {v["title"][:60]}')


if __name__ == "__main__":
    main()
