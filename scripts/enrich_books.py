"""Шаг 4. Где купить: ищем каждую книгу в «Московском Доме книги» (mdk-arbat.ru)
и в магазине «Москва» (moscowbooks.ru) через XMLRiver.

Один платный запрос XMLRiver на книгу.

  -> data/books_links.json  (resume)

Запуск:  python scripts/enrich_books.py --limit 80
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.services.xmlriver_client import QuotaExhausted, XmlRiver  # noqa: E402

SHOPS = {
    # магазины
    "mdk-arbat.ru": "Московский Дом книги",
    "moscowbooks.ru": "Книжный магазин «Москва»",
    "labirint.ru": "Лабиринт",
    "chitai-gorod.ru": "Читай-город",
    "book24.ru": "Book24",
    "bookvoed.ru": "Буквоед",
    "respublica.ru": "Республика",
    "podpisnie.ru": "Подписные издания",
    "falanster.ru": "Фаланстер",
    "ozon.ru": "Ozon",
    "wildberries.ru": "Wildberries",
    # подписки и электронные книги
    "litres.ru": "Литрес",
    "books.yandex.ru": "Яндекс Книги",
    "stroki.mts.ru": "Строки",
    "author.today": "Author.Today",
    # сайты издательств
    "ast.ru": "АСТ",
    "eksmo.ru": "Эксмо",
    "alpinabook.ru": "Альпина",
    "mann-ivanov-ferber.ru": "МИФ",
    "azbooka.ru": "Азбука-Аттикус",
    "bombora.ru": "Бомбора",
    "corpus.ru": "Corpus",
    "nlobooks.ru": "НЛО",
    "individuumbooks.ru": "Individuum",
    "polyandria.ru": "Поляндрия",
    "samokatbook.ru": "Самокат",
    "rosman.ru": "Росмэн",
    "clever-media.ru": "Клевер",
    "peterbook.ru": "Питер",
    "piter.com": "Питер",
    "veche.ru": "Вече",
    "prosv.ru": "Просвещение",
}
PRICE = re.compile(r"(\d[\d\s]{1,6})\s*(?:₽|руб)", re.I)


def host(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", url)
    return (m.group(1) if m else "").lower()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--mdk-pass", action="store_true",
                    help="второй проход: искать только по mdk-arbat.ru для книг, "
                         "у которых «Дом книги» ещё не найден")
    ap.add_argument("--wide-pass", action="store_true",
                    help="третий проход: свободный поиск без site:, чтобы поймать другие "
                         "магазины и сайты издательств")
    args = ap.parse_args()

    books = json.loads((ROOT / "data" / "books.json").read_text(encoding="utf-8"))["books"]
    out_path = ROOT / "data" / "books_links.json"
    done = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    if args.mdk_pass:
        targets = [b for b in books[: args.limit]
                   if b["title"] in done
                   and not any(o["shop"] == "Московский Дом книги" for o in done[b["title"]]["offers"])]
    elif args.wide_pass:
        targets = [b for b in books[: args.limit] if b["title"] in done]
    else:
        targets = [b for b in books[: args.limit] if b["title"] not in done]
    print(f"книг к обработке: {len(targets)} (уже есть {len(done)}) — {len(targets)} платных запросов XMLRiver")
    if not targets:
        return

    x = XmlRiver("google")
    queries = {}
    for b in targets:
        if args.mdk_pass:
            q = f'site:mdk-arbat.ru "{b["title"]}"'
        elif args.wide_pass:
            q = f'«{b["title"]}» {b["author"]} книга купить издательство'.strip()
        else:
            q = f'{b["title"]} {b["author"]} книга купить site:mdk-arbat.ru OR site:moscowbooks.ru OR site:labirint.ru'.strip()
        queries[q] = b
    try:
        res = x.search_many(queries.keys(), workers=args.workers)
    except QuotaExhausted as e:
        print(f"XMLRiver: лимиты исчерпаны ({e}). Сохраняю что есть.")
        res = {}

    for q, docs in res.items():
        b = queries[q]
        offers = []
        for d in docs:
            h = host(d["url"])
            shop = next((v for k, v in SHOPS.items() if h == k or h.endswith("." + k)), None)
            if not shop:
                continue
            price = PRICE.search(d["snippet"] or "")
            offers.append({
                "shop": shop, "url": d["url"], "title": d["title"],
                "price": price.group(1).replace(" ", "") if price else None,
            })
        if args.mdk_pass or args.wide_pass:    # дополнительные проходы только дополняют
            offers = done[b["title"]]["offers"] + offers
        # «Дом книги» — первым, как просили
        seen = set()
        uniq = []
        for o in offers:
            if o["url"] in seen:
                continue
            seen.add(o["url"])
            uniq.append(o)
        uniq.sort(key=lambda o: (o["shop"] != "Московский Дом книги", o["shop"]))
        done[b["title"]] = {**b, "offers": uniq}

    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    withshop = sum(1 for v in done.values() if v["offers"])
    print(f"Готово: {len(done)} книг, у {withshop} есть ссылки в магазины -> {out_path}")


if __name__ == "__main__":
    main()
