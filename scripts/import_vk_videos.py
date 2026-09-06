"""Шаг 6b. Записи трансляций ярмарки из VK Видео и их привязка к программе.

Основной источник — data/vk/vk_api.json (его собирает vk_grab_api.py через
VK API в живом браузере): там id, названия, длительность, просмотры, даты
и готовая ссылка плеера с хешем.

Запасной источник — текстовый список со страницы канала в формате
«Название|Длительность|Просмотры»: годится, когда браузерного моста нет.

В обоих случаях скрипт сам сопоставляет ролики с событиями программы
по названию.

  -> data/vk_videos.json

Запуск:
  python scripts/import_vk_videos.py                       # из vk_api.json
  python scripts/import_vk_videos.py data/vk/список.txt    # из текстового списка
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]

CHANNEL = "https://vkvideo.ru/@mmkya/all"
API_FILE = ROOT / "data" / "vk" / "vk_api.json"


def norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"\.(mp4|mov)$", "", s)
    return re.sub(r"[^a-zа-я0-9 ]+", " ", s).strip()


def views_to_int(s: str) -> int | None:
    m = re.search(r"([\d,]+)\s*(тыс|млн)?", s or "")
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return int(n * {"тыс": 1000, "млн": 1_000_000}.get(m.group(2) or "", 1))


def embed_url(player: str) -> str:
    """Из ссылки, которую отдаёт video.get, собираем ту, что реально встраивается.

    Проверено 6 сентября 2026:
      * без параметра `hash` плеер пишет «Видео недоступно»;
      * `__ref` и `api_hash` из ответа API привязаны к сессии — на чужой странице
        они мешают, их выкидываем;
      * хост должен быть `vk.com`: `vkvideo.ru/video_ext.php` отдаёт не плеер.
    """
    if not player:
        return ""
    q = parse_qs(urlparse(player).query)
    oid, vid, h = q.get("oid", [""])[0], q.get("id", [""])[0], q.get("hash", [""])[0]
    if not (oid and vid and h):
        return ""
    return f"https://vk.com/video_ext.php?oid={oid}&id={vid}&hash={h}&hd=2"


def from_api() -> list[dict]:
    data = json.loads(API_FILE.read_text(encoding="utf-8"))
    out = []
    for v in data["videos"]:
        out.append({
            "title": v["title"],
            "duration": v.get("duration_str", ""),
            "views": v.get("views"),
            "date": v.get("date_iso", "")[:10],
            "vk_id": f'video{v["owner"]}_{v["id"]}',
            "url": v.get("url", ""),
            "embed": embed_url(v.get("player", "")),
            "thumb": v.get("thumb", ""),
        })
    return out


def from_text(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = [x.strip() for x in line.split("|")] + ["", ""]
        meta = p[2]
        out.append({
            "title": p[0], "duration": p[1], "views": views_to_int(meta),
            "age": meta.split("·")[-1].strip() if "·" in meta else meta,
        })
    return out


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if src:
        videos, origin = from_text(src), f"текстовый список ({src.name})"
    elif API_FILE.exists():
        videos, origin = from_api(), "VK API через browser-bridge"
    else:
        raise SystemExit("Нет data/vk/vk_api.json — сначала: python scripts/vk_grab_api.py")

    program = json.loads((ROOT / "data" / "program.json").read_text(encoding="utf-8"))
    events, refs = program["events"], program["refs"]

    matched = 0
    for v in videos:
        key = norm(v["title"])
        best, score = None, 0.0
        for e in events:
            r = SequenceMatcher(None, key, norm(e["title"])).ratio()
            if r > score:
                best, score = e, r
        v["event"] = None
        if best and score >= 0.72:
            matched += 1
            v["event"] = {
                "id": best["id"], "title": best["title"], "date": best["date"],
                "day": (refs.get(best["date"]) or {}).get("title", ""),
                "venue": best["venue"]["title"], "score": round(score, 2),
            }

    videos.sort(key=lambda v: -(v["views"] or 0))
    out = {
        "channel": CHANNEL,
        "source": origin,
        "fetched": datetime.now(timezone.utc).date().isoformat(),
        "count": len(videos),
        "matched": matched,
        "with_id": sum(1 for v in videos if v.get("vk_id")),
        "videos": videos,
    }
    path = ROOT / "data" / "vk_videos.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f'Готово: {len(videos)} роликов ({origin}), {matched} привязаны к программе, '
          f'{out["with_id"]} с плеером -> {path}')
    for v in videos[:5]:
        ev = v["event"]["title"][:44] if v["event"] else "— нет события —"
        print(f'  {str(v["views"]):>6}  {v["title"][:48]:<50} -> {ev}')


if __name__ == "__main__":
    main()
