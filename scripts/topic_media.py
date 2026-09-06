"""Шаг 11a. Медиа под статьи по темам: ролики с YouTube и обложки книг.

Что берём и почему именно это:
  * YouTube — по 2–3 ролика на тему, ищем через XMLRiver (`site:youtube.com`).
    Встраивается без ключей, id достаётся из ссылки `watch?v=`.
  * Обложки книг — `og:image` со страницы того самого магазина, на который
    статья и так ссылается. Это карточка товара, которую магазин сам отдаёт
    для превью ссылки; чужие картинки из поиска не берём.
  * Кадры записей трансляций уже лежат в data/vk_videos.json — их подставляет
    генератор сайта.

  -> data/topics/media.json  (resume: собранное не перезапрашивается)

Запуск:  python scripts/topic_media.py [--videos] [--covers] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.xmlriver_client import QuotaExhausted, XmlRiver  # noqa: E402

OUT = ROOT / "data" / "topics" / "media.json"
TOPICS = ROOT / "data" / "topics"

YT_ID = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})")
OG = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.I)
OG2 = re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
# brotli на больших карточках упирался в память, а нужные meta лежат в начале <head>
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip"}
HEAD_BYTES = 400_000

# по каким запросам искать ролики: тема ярмарки -> человеческий поисковый запрос
QUERIES = {
    "ПРОГРАММА ДЛЯ ДЕТЕЙ": ["детская литература что читать детям лекция",
                            "как привить ребёнку любовь к чтению"],
    "НОН-ФИКШН": ["нон-фикшн литература лекция научпоп книги",
                  "как выбирать научно-популярные книги"],
    "ХУДОЖЕСТВЕННАЯ ЛИТЕРАТУРА": ["современная русская проза лекция",
                                  "что читать современная литература разбор"],
    "КНИГА +": ["экранизация книги как это работает лекция",
                "книга и кино адаптация литературы"],
    "МОЛОДЁЖНАЯ ЛИТЕРАТУРА": ["young adult литература разбор жанра",
                              "самиздат как стать писателем молодёжная проза"],
    "ПОЭЗИЯ": ["современная русская поэзия лекция",
               "как читать стихи поэзия XXI века"],
    "ДЕЛОВАЯ ПРОГРАММА": ["книжный рынок России издательский бизнес",
                          "как работает издательство изнутри"],
    "КОМИКСЫ": ["комиксы манга индустрия России лекция",
                "как создаются комиксы графический роман"],
}


def load() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}


def save(d: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def find_videos(limit: int) -> None:
    data = load()
    x = XmlRiver("google")
    for topic, queries in list(QUERIES.items())[:limit]:
        slot = data.setdefault(topic, {})
        if slot.get("videos"):
            continue
        found, seen = [], set()
        try:
            res = x.search_many([f"site:youtube.com {q}" for q in queries], workers=4)
        except QuotaExhausted as e:
            print(f"XMLRiver: {e}")
            break
        for docs in res.values():
            for d in docs:
                m = YT_ID.search(d["url"])
                if not m or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                found.append({"id": m.group(1), "title": d["title"],
                              "url": f"https://www.youtube.com/watch?v={m.group(1)}",
                              "embed": f"https://www.youtube.com/embed/{m.group(1)}",
                              "snippet": (d["snippet"] or "")[:200]})
        slot["videos"] = found[:6]
        print(f"  {topic}: роликов {len(slot['videos'])}")
        save(data)


# когда карточки товара нет, магазин отдаёт в og:image свой логотип-заглушку.
# Такие «обложки» брать нельзя: в статье это будет не книга, а картинка магазина.
PLACEHOLDER = ("main-cover.jpg", "logomini.png", "bk-logo-social", "no-photo",
               "nophoto", "placeholder", "default-cover", "og-default",
               "author-og-image", "goodssets", "yandexlabels")


OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I)


def norm_title(s: str) -> str:
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", " ", s).strip()


def title_matches(ours: str, theirs: str) -> bool:
    """Совпадает ли название книги с тем, что стоит на карточке магазина.

    Нужно, потому что ссылки на магазины найдены поиском, и на короткое название
    вроде «Былины» магазин отдаёт совсем другую книгу — а в статье под подписью
    окажется чужая обложка.
    """
    a, b = norm_title(ours), norm_title(theirs)
    if not a or not b:
        return False
    if a in b or b.startswith(a):
        return True
    wa = [w for w in a.split() if len(w) > 3]
    return bool(wa) and sum(w in b for w in wa) / len(wa) >= 0.75


def og_image(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, stream=True)
        if r.status_code != 200:
            return ""
        html = r.raw.read(HEAD_BYTES, decode_content=True).decode(
            r.encoding or "utf-8", "ignore")
        m = OG.search(html) or OG2.search(html)
        if not m:
            return ""
        img = m.group(1).strip()
        if img.startswith("//"):
            img = "https:" + img
        if not img.startswith("http") or any(x in img for x in PLACEHOLDER):
            return ""
        if img.count("http") > 1:          # встречается склейка двух адресов
            return ""
        return img
    except requests.RequestException:
        return ""


def og_pair(url: str) -> tuple[str, str]:
    """Картинка и заголовок карточки — чтобы проверить, та ли это книга."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=25, stream=True)
        if r.status_code != 200:
            return "", ""
        html = r.raw.read(HEAD_BYTES, decode_content=True).decode(
            r.encoding or "utf-8", "ignore")
        m = OG.search(html) or OG2.search(html)
        img = (m.group(1).strip() if m else "")
        if img.startswith("//"):
            img = "https:" + img
        if (not img.startswith("http") or img.count("http") > 1
                or any(x in img for x in PLACEHOLDER)):
            img = ""
        t = OG_TITLE.search(html)
        return img, (t.group(1) if t else "")
    except requests.RequestException:
        return "", ""


def find_covers(limit: int) -> None:
    data = load()
    links = json.loads((ROOT / "data" / "books_links.json").read_text(encoding="utf-8"))

    for path in sorted(TOPICS.glob("*.json")):
        if path.name == "media.json":
            continue
        t = json.loads(path.read_text(encoding="utf-8"))
        topic = t["topic"]
        slot = data.setdefault(topic, {})
        if slot.get("covers"):
            continue

        # og:image отдают не все: у «Дома книги» его нет, а он в списке идёт первым,
        # поэтому по каждой книге перебираем магазины, пока картинка не найдётся
        WITH_OG = ("moscowbooks.ru", "labirint.ru", "chitai-gorod.ru",
                   "bookvoed.ru", "litres.ru", "eksmo.ru")
        want = []
        for title, _ in t["books"][:limit]:
            offers = [o for o in (links.get(title) or {}).get("offers", [])
                      if any(s in o["url"] for s in WITH_OG)]
            if offers:
                want.append((title, offers[:3]))

        def first_cover(w):
            title = w[0]
            for o in w[1]:
                img, page_title = og_pair(o["url"])
                if img and title_matches(title, page_title):
                    return o, img
            return None, ""

        covers = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            for (title, _), (offer, img) in zip(want, pool.map(first_cover, want)):
                if img:
                    covers.append({"title": title, "shop": offer["shop"],
                                   "url": offer["url"], "image": img})
        slot["covers"] = covers
        print(f"  {topic}: обложек {len(covers)} из {len(want)}")
        save(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", action="store_true")
    ap.add_argument("--covers", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()
    if not (args.videos or args.covers):
        args.videos = args.covers = True
    if args.videos:
        print("Ролики с YouTube:")
        find_videos(args.limit)
    if args.covers:
        print("Обложки книг:")
        find_covers(args.limit)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
