"""Шаг 6d. Список видео сообщества ярмарки — через VK API из живого браузера.

Почему так, а не иначе:
  * `vkvideo.ru/@mmkya/all` без авторизации редиректит на errorCode=11300;
  * в фоновой вкладке ленивая подгрузка списка не срабатывает (Chrome душит
    таймеры невидимых вкладок), скроллом достаётся только первая тройка роликов;
  * плеер `video_ext.php` без параметра `hash` показывает «Видео недоступно».

Зато сама страница VK Видео ходит в `api.vkvideo.ru/method/*` со своим
веб-токеном. Мы выполняем `video.get` прямо в контексте страницы через
browser-bridge: токен остаётся в браузере пользователя и наружу не уходит,
а к нам приезжает готовый список с полем `player` — это и есть ссылка
для встраивания вместе с хешем.

Подготовка:
    python ~/.claude/skills/browser-bridge/bridge.py serve     # в фоне
    # включить мост в попапе расширения
    python ~/.claude/skills/browser-bridge/bridge.py pin "https://vkvideo.ru/@mmkya/all"

Запуск:  python scripts/vk_grab_api.py --since 2026-08-27
  -> data/vk/vk_api.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path.home() / ".claude" / "skills" / "browser-bridge" / "bridge.py"
OWNER = -98267658          # сообщество ММКЯ, id виден в ссылках на альбомы ВК
OUT = ROOT / "data" / "vk" / "vk_api.json"

# Токен берётся из localStorage самой страницы и остаётся там же:
# в наш процесс возвращается только список роликов.
JS = """(async () => {
  const key = Object.keys(localStorage).find(k => /web_token:login:auth$/.test(k));
  if (!key) return {err: 'нет веб-токена: откройте vkvideo.ru и войдите'};
  const tok = JSON.parse(localStorage.getItem(key)).access_token;
  const out = [];
  for (let offset = 0; offset < %(max)d; offset += 200) {
    const p = new URLSearchParams({owner_id: '%(owner)d', count: '200',
        offset: String(offset), v: '5.207', access_token: tok, lang: 'ru'});
    const r = await fetch('https://api.vkvideo.ru/method/video.get?' + p);
    const j = await r.json();
    if (j.error) return {err: j.error.error_msg, code: j.error.error_code};
    for (const v of j.response.items) {
      // обложка: берём самую крупную из image[], иначе кадр из first_frame[]
      const pics = (v.image || []).concat(v.first_frame || [])
          .sort((a, b) => (b.width || 0) - (a.width || 0));
      out.push({
        id: v.id, owner: v.owner_id, title: v.title, duration: v.duration,
        views: v.views, date: v.date, player: v.player || '',
        thumb: pics.length ? pics[0].url : ''
      });
    }
    if (out.length >= j.response.count) break;
  }
  return {total: out.length, items: out};
})()"""


def bridge_eval(js: str, timeout: int = 180) -> dict:
    r = subprocess.run([sys.executable, str(BRIDGE), "eval", js],
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=timeout, env={"PYTHONUTF8": "1", **os.environ})
    out = (r.stdout or "").strip()
    if "{" not in out:
        raise SystemExit(f"Мост не ответил: {out or r.stderr[:200]}")
    return json.loads(out[out.find("{"):])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-08-27", help="брать ролики не старше этой даты")
    ap.add_argument("--max", type=int, default=600, help="сколько роликов пролистать")
    args = ap.parse_args()

    res = bridge_eval(JS % {"owner": OWNER, "max": args.max})
    if res.get("err"):
        raise SystemExit(f'VK API: {res["err"]}')

    since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    items = [v for v in res["items"] if (v.get("date") or 0) >= since]
    items.sort(key=lambda v: -(v.get("date") or 0))

    for v in items:
        d = v.get("duration") or 0
        v["duration_str"] = (f"{d // 3600}:{d % 3600 // 60:02d}:{d % 60:02d}" if d >= 3600
                             else f"{d // 60}:{d % 60:02d}") if d else ""
        v["url"] = f'https://vkvideo.ru/video{v["owner"]}_{v["id"]}'
        v["date_iso"] = datetime.fromtimestamp(v["date"], timezone.utc).isoformat()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"owner": OWNER, "since": args.since,
                               "total_in_community": res["total"],
                               "count": len(items), "videos": items},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    with_player = sum(1 for v in items if v.get("player"))
    print(f'В сообществе роликов: {res["total"]}. С {args.since}: {len(items)}, '
          f"со ссылкой плеера: {with_player}")
    for v in items[:8]:
        print(f'  {v["date_iso"][:10]}  {v["duration_str"]:>8}  {v["title"][:62]}')
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
