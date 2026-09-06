"""Шаг 1d. Сводит контакты участников: карточка с карты ярмарки + обход сайтов.

Карта ярмарки даёт почту, телефон и адрес, но не даёт соцсетей. Скилл
contact-scraper обходит сайт каждого участника («главная» + «контакты/о нас»)
и добирает Telegram, MAX, VK, WhatsApp и дополнительные адреса.

  вход:  data/contacts/out/contacts.jsonl  (результат скилла)
  выход: data/exhibitors.json              (обновляется на месте, поле contacts)
         data/tg_channels.json             (найденные телеграм-каналы участников)

Запуск:  python scripts/merge_contacts.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

# как поля скилла ложатся в наши
NETWORKS = {
    "telegram": "Telegram", "max": "MAX", "vk": "ВКонтакте", "whatsapp": "WhatsApp",
    "ok": "Одноклассники", "instagram": "Instagram", "facebook": "Facebook",
    "youtube": "YouTube", "linkedin": "LinkedIn", "x": "X", "wechat": "WeChat",
    "line": "Line", "xing": "Xing",
}
TG_USER = re.compile(r"t\.me/(?:s/)?([A-Za-z0-9_]{4,32})/?$")
BAD_TG = {"share", "joinchat", "addstickers", "proxy", "iv"}


def domain(url: str) -> str:
    try:
        h = urlparse(url if url.startswith("http") else "https://" + url).hostname or ""
    except ValueError:
        return ""
    return h.lower().removeprefix("www.")


def as_list(v) -> list[str]:
    """Строку режем только по разделителям списка, но НЕ по пробелам:
    иначе «+7 (916) 123-45-67» распадётся на три куска."""
    if not v:
        return []
    if isinstance(v, str):
        return [x.strip() for x in re.split(r"[;,\n]+", v) if x.strip()]
    return [str(x).strip() for x in v if str(x).strip()]


def main() -> None:
    src = ROOT / "data" / "contacts" / "out" / "contacts.jsonl"
    if not src.exists():
        raise SystemExit(f"Нет {src} — сначала прогоните скилл contact-scraper "
                         "(см. README, шаг «Контакты участников»).")

    scraped = {}
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        d = domain(rec.get("site") or rec.get("url") or "")
        if d:
            scraped[d] = rec

    path = ROOT / "data" / "exhibitors.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data["exhibitors"]

    tg_channels = {}
    stats = {"matched": 0, "with_social": 0, "with_email": 0, "with_tg": 0}

    for x in items:
        d = domain(x.get("website") or "")
        rec = scraped.get(d)
        emails = [e for e in as_list(x.get("email")) if "@" in e]
        socials: list[dict] = []

        if rec:
            stats["matched"] += 1
            for e in as_list(rec.get("emails") or rec.get("email")):
                if "@" in e and e.lower() not in {y.lower() for y in emails}:
                    emails.append(e)
            for key, label in NETWORKS.items():
                for url in as_list(rec.get(key)):
                    if not url.startswith("http"):
                        url = "https://" + url.lstrip("/")
                    socials.append({"network": label, "url": url})

        # дедуп по url, одна ссылка на сеть
        seen_url, seen_net, uniq = set(), set(), []
        for s in socials:
            if s["url"] in seen_url or s["network"] in seen_net:
                continue
            seen_url.add(s["url"])
            seen_net.add(s["network"])
            uniq.append(s)

        x["contacts"] = {
            "emails": emails,
            "phones": as_list(x.get("phone")),
            "social": uniq,
        }
        if uniq:
            stats["with_social"] += 1
        if emails:
            stats["with_email"] += 1

        for s in uniq:
            if s["network"] != "Telegram":
                continue
            m = TG_USER.search(s["url"])
            if not m or m.group(1).lower() in BAD_TG:
                continue
            stats["with_tg"] += 1
            tg_channels[m.group(1)] = {
                "username": m.group(1),
                "exhibitor": x["name"],
                "group": x.get("group", ""),
                "url": s["url"],
            }
            break

    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # канал самой ярмарки идёт первым — он опорный для разбора
    channels = {"mibf_info": {"username": "mibf_info", "exhibitor": "ММКЯ (канал ярмарки)",
                              "group": "Организатор", "url": "https://t.me/mibf_info"}}
    channels.update(dict(sorted(tg_channels.items())))
    (ROOT / "data" / "tg_channels.json").write_text(
        json.dumps({"count": len(channels), "channels": list(channels.values())},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"Участников: {len(items)}, сайты обойдены у {stats['matched']}")
    print(f"  с почтой: {stats['with_email']} · с соцсетями: {stats['with_social']} "
          f"· с телеграм-каналом: {stats['with_tg']}")
    print(f"  каналов к разбору: {len(channels)} -> data/tg_channels.json")


if __name__ == "__main__":
    main()
