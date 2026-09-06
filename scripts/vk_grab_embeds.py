"""Шаг 6d. Снимает id, названия и embed-хеши роликов VK из живого браузера.

Зачем так: VK не отдаёт список видео сообщества без авторизации, а плеер
video_ext.php без параметра hash показывает «Видео недоступно». Хеш выдаётся
только в диалоге «Поделиться → Встроить» на странице ролика.

Поэтому работаем через browser-bridge в настоящем Chrome пользователя:

    python ~/.claude/skills/browser-bridge/bridge.py serve      # в фоне
    # включить мост в попапе расширения, затем:
    python scripts/vk_grab_embeds.py --list                     # собрать id со страницы канала
    python scripts/vk_grab_embeds.py --embeds                   # добрать hash по каждому ролику

  -> data/vk/vk_embeds.json  (resume: уже снятые ролики пропускаются)

Дальше: python scripts/import_vk_ids.py data/vk/vk_embeds.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path.home() / ".claude" / "skills" / "browser-bridge" / "bridge.py"
CHANNEL = "https://vkvideo.ru/@mmkya/all"
OUT = ROOT / "data" / "vk" / "vk_embeds.json"

EMBED = re.compile(r"video_ext\.php\?oid=(-?\d+)&id=(\d+)&hash=([a-f0-9]+)")


def bridge(*args: str, timeout: int = 120) -> dict:
    r = subprocess.run([sys.executable, str(BRIDGE), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=timeout, env={"PYTHONUTF8": "1", **__import__("os").environ})
    out = (r.stdout or "").strip()
    try:
        return json.loads(out[out.find("{"):]) if "{" in out else {"raw": out}
    except json.JSONDecodeError:
        return {"raw": out, "err": (r.stderr or "")[:200]}


def load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def save(data: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# --- шаг 1: id и названия со страницы канала ------------------------------
# Скроллим короткими порциями: длинный async-скрипт в eval роняет расширение
# (проверено — мост отваливается на 30-секундном цикле).
GRAB = """(() => {
  window.__acc = window.__acc || {};
  for (const a of document.querySelectorAll('a[href*="/video-"]')) {
    const m = (a.getAttribute('href')||'').match(/video(-?\\d+)_(\\d+)/);
    if (!m) continue;
    let t = (a.getAttribute('title')||'').trim();
    if (!t) {
      const card = a.closest('li,article,div');
      const lines = ((card && card.innerText)||'').split('\\n').map(s=>s.trim())
        .filter(s=>s && !/^\\d+:\\d/.test(s) && !/просмотр|назад|смотрит|подписч/i.test(s));
      t = lines[0]||'';
    }
    const prev = window.__acc[m[0]];
    if (!prev || (t && !prev.title)) window.__acc[m[0]] = {oid:m[1], vid:m[2], title:t};
  }
  // у VK Видео своя прокручиваемая область, окно почти не двигается
  const sc = [...document.querySelectorAll('.vkuiCustomScrollView__host')]
      .find(e => e.scrollHeight > e.clientHeight + 100) || document.scrollingElement;
  sc.scrollTop += sc.clientHeight * 0.85;
  window.scrollBy(0, window.innerHeight * 0.85);
  return {n: Object.keys(window.__acc).length, y: Math.round(sc.scrollTop),
          h: sc.scrollHeight};
})()"""


def collect_list(steps: int) -> None:
    print(bridge("pin", CHANNEL).get("ok") and f"открыл {CHANNEL}" or "не удалось открыть")
    time.sleep(6)
    seen = 0
    for i in range(steps):
        r = bridge("eval", GRAB, timeout=60)
        n = r.get("n")
        if n is None:
            print(f"  шаг {i}: {r}")
            break
        if i % 5 == 0 or n != seen:
            print(f"  шаг {i}: роликов {n}, прокрутка {r.get('y')}/{r.get('h')}")
        seen = n
        time.sleep(1.2)

    got = bridge("eval", "window.__acc", timeout=60)
    items = {k: v for k, v in got.items() if isinstance(v, dict) and v.get("vid")}
    data = load()
    for k, v in items.items():
        data.setdefault(k, {}).update({"id": k, "oid": v["oid"], "vid": v["vid"],
                                       "title": v.get("title", "")})
    save(data)
    print(f"Собрано роликов: {len(items)}, всего в файле: {len(data)} -> {OUT}")


# --- шаг 2: hash из диалога «Поделиться → Встроить» ------------------------
OPEN_SHARE = """(() => {
  const pick = (label) => [...document.querySelectorAll('*')]
      .filter(e => (e.innerText||'').trim() === label && e.children.length < 3).pop();
  const share = pick('Поделиться');
  if (share) (share.closest('button,[role=button],a,div[tabindex]')||share).click();
  return {clicked: !!share};
})()"""

OPEN_EMBED = """(() => {
  const pick = (label) => [...document.querySelectorAll('*')]
      .filter(e => (e.innerText||'').trim() === label && e.children.length < 3).pop();
  const emb = pick('Встроить');
  if (emb) (emb.closest('button,[role=button],a,div[tabindex]')||emb).click();
  return {clicked: !!emb};
})()"""

READ_EMBED = """(() => {
  const v = [...document.querySelectorAll('textarea,input')]
      .map(e => e.value).find(x => x && x.includes('video_ext.php'));
  return {code: v || ''};
})()"""


def collect_embeds(limit: int) -> None:
    data = load()
    todo = [v for v in data.values() if not v.get("hash")][:limit]
    print(f"снять hash: {len(todo)} (уже есть {sum(1 for v in data.values() if v.get('hash'))})")

    for i, rec in enumerate(todo, 1):
        url = f'https://vkvideo.ru/video{rec["oid"]}_{rec["vid"]}'
        bridge("pin", url)
        time.sleep(5)
        if not rec.get("title"):
            t = bridge("eval", "({t: document.title})")
            rec["title"] = (t.get("t") or "").replace(" | VK Видео", "").strip()
        bridge("eval", OPEN_SHARE)
        time.sleep(1.5)
        bridge("eval", OPEN_EMBED)
        time.sleep(1.5)
        code = bridge("eval", READ_EMBED).get("code", "")
        m = EMBED.search(code)
        if m:
            rec["hash"] = m.group(3)
            print(f'  {i}/{len(todo)}  {rec["title"][:50]}  hash={m.group(3)}')
        else:
            print(f'  {i}/{len(todo)}  {rec["title"][:50]}  — hash не считался')
        save(data)
        time.sleep(0.5)

    ok = sum(1 for v in data.values() if v.get("hash"))
    print(f"\nГотово: hash у {ok} из {len(data)} роликов -> {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="собрать id со страницы канала")
    ap.add_argument("--embeds", action="store_true", help="добрать hash по каждому ролику")
    ap.add_argument("--steps", type=int, default=60, help="сколько шагов прокрутки")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    if bridge("status").get("extension_connected") is not True:
        raise SystemExit("Мост не подключён: запустите bridge.py serve и включите мост в попапе.")
    if args.list:
        collect_list(args.steps)
    if args.embeds:
        collect_embeds(args.limit)
    if not (args.list or args.embeds):
        raise SystemExit("Укажите --list и/или --embeds")


if __name__ == "__main__":
    main()
