"""Шаг 5. Собирает статический сайт-разбор ярмарки в site/.

Всё генерится из data/*.json — никакого бэкенда, папку site/ можно положить
на GitHub Pages как есть.

Страницы:
  index.html            — разбор ярмарки в цифрах
  program.html          — вся программа, фильтры по дню/площадке/жанру, поиск
  event/<id>.html       — страница на каждое событие (509 шт.)
  exhibitors.html       — 243 участника со стендами
  books.html            — сквозной список книг + где купить
  people.html           — спикеры и их соцсети
  map.html              — мастерплан «Гостиного Двора»
  press.html            — разбор пресс-релиза
  stroki.html           — «Строки» (КИОН) против Литрес и других
  video.html            — видео и трансляции ярмарки

Запуск:  python scripts/build_site.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SITE = ROOT / "site"
CONTENT = ROOT / "content"

NAV = [
    ("index.html", "Разбор"),
    ("program.html", "Программа"),
    ("exhibitors.html", "Участники"),
    ("books.html", "Книги"),
    ("people.html", "Спикеры"),
    ("articles.html", "Статьи"),
    ("telegram.html", "Телеграм"),
    ("tg-feed.html", "Лента"),
    ("map.html", "Карта"),
    ("press.html", "Пресс-релиз"),
    ("stroki.html", "Строки vs Литрес"),
    ("video.html", "Видео"),
]

E = html.escape


def load(name: str, default=None):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()


def social_links(entry: dict | None, limit: int = 5) -> str:
    """Одна ссылка на соцсеть — выдача часто отдаёт по три профиля в одной сети."""
    seen, out = set(), []
    for s in (entry or {}).get("social", []):
        if s["network"] in seen:
            continue
        seen.add(s["network"])
        out.append(f'<a href="{E(s["url"])}" rel="nofollow noopener" target="_blank">{E(s["network"])}</a>')
        if len(out) >= limit:
            break
    return " ".join(out)


MD_LINK = re.compile(r"\[([^\]]{1,160})\]\((https?://[^)\s]+)\)")
MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
BARE_URL = re.compile(r"(?<![\"'>=])(https?://[^\s<>\"']{6,})")


def tg_html(text: str) -> str:
    """Телеграм отдаёт разметку текстом: [подпись](url), **жирный**, голые ссылки.
    Превращаем её в настоящий HTML, экранируя всё остальное.

    Ссылки вынимаются в плейсхолдеры ДО экранирования: иначе «&» внутри url
    станет «&amp;» и ссылка сломается."""
    links: list[str] = []

    def stash(href: str, label: str) -> str:
        # жирный внутри подписи ссылки обрабатывается тут же: до общего прохода
        # по тексту подпись уже спрятана в плейсхолдер и звёздочки бы остались
        text_label = MD_BOLD.sub(lambda m: f"<b>{E(m.group(1))}</b>", E(label))
        links.append(f'<a href="{E(href, quote=True)}" rel="nofollow noopener" '
                     f'target="_blank">{text_label}</a>')  # noqa: E501
        return f"@@L{len(links) - 1}@@"

    text = MD_LINK.sub(lambda m: stash(m.group(2), m.group(1)), text)
    text = BARE_URL.sub(lambda m: stash(m.group(0), m.group(0)), text)

    out = E(text)
    out = MD_BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", out)
    return re.sub(r"@@L(\d+)@@", lambda m: links[int(m.group(1))], out)


def slug(name: str) -> str:
    """Транслит имени в имя файла: у 1200 человек нужны стабильные адреса."""
    tbl = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
           "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
           "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
           "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
           "ю": "yu", "я": "ya"}
    s = "".join(tbl.get(c, c) for c in name.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "person"

# версия в ссылке на стили: без неё браузер держит старый CSS после правок вёрстки
CSS_VER = ""


def page(title: str, body: str, *, depth: int = 0, description: str = "") -> str:
    up = "../" * depth
    nav = "".join(f'<a href="{up}{href}">{E(label)}</a>' for href, label in NAV)
    return f"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)} — ММКЯ-2026, разбор</title>
<meta name="description" content="{E(description or title)}">
<link rel="stylesheet" href="{up}assets/style.css?v={CSS_VER}">
</head><body>
<header class="top">
  <a class="brand" href="{up}index.html">ММКЯ&nbsp;2026 <span>разбор ярмарки</span></a>
  <nav>{nav}</nav>
</header>
<main>{body}</main>
<footer>
  <p>Независимый разбор 39-й Московской международной книжной ярмарки (2–6 сентября 2026, «Гостиный Двор»).
  Данные собраны из открытого API сайта <a href="https://events.mibf.info/2026/program">events.mibf.info</a>,
  пресс-релиза организаторов и поисковой выдачи. Это не официальный сайт ярмарки.</p>
</footer>
</body></html>"""


CSS = """
:root{--bg:#fbfaf7;--fg:#1a1917;--mut:#6d6a63;--line:#e2ddd2;--card:#fff;--acc:#8c2f24;--acc2:#1f5c4a;--chip:#f0ece2}
@media (prefers-color-scheme:dark){:root{--bg:#16151a;--fg:#eceae4;--mut:#9d9a92;--line:#2e2c33;--card:#1e1d23;--acc:#e2735f;--acc2:#6bbfa2;--chip:#282730}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 Georgia,"Iowan Old Style",serif}
a{color:var(--acc)}
main{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
.top{border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:12px 22px;align-items:baseline;padding:12px 20px}
.brand{font-weight:700;font-size:19px;text-decoration:none;color:var(--fg)}
.brand span{font-weight:400;font-size:13px;color:var(--mut)}
.top nav{display:flex;flex-wrap:wrap;gap:14px;font:14px/1 system-ui,sans-serif}
.top nav a{color:var(--mut);text-decoration:none;padding:4px 0;border-bottom:2px solid transparent}
.top nav a:hover{color:var(--acc);border-color:var(--acc)}
h1{font-size:34px;line-height:1.15;margin:.2em 0 .4em}
h2{font-size:24px;margin:1.8em 0 .6em;border-bottom:1px solid var(--line);padding-bottom:.3em;scroll-margin-top:70px}
h3{font-size:18px;margin:1.4em 0 .4em}
.lead{font-size:19px;color:var(--mut)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:block}
a.stat{text-decoration:none;color:inherit;transition:border-color .15s,transform .15s}
a.stat:hover{border-color:var(--acc);transform:translateY(-2px)}
a.stat:hover b{text-decoration:underline}
.stat b{display:block;font-size:30px;line-height:1.1;color:var(--acc)}
.stat span{font:13px/1.3 system-ui,sans-serif;color:var(--mut)}
table{border-collapse:collapse;width:100%;font:14px/1.5 system-ui,sans-serif;margin:14px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600}
.wrap{overflow-x:auto}
.bar{height:8px;background:var(--acc);border-radius:4px;display:block;min-width:2px}
.chip{display:inline-block;background:var(--chip);border-radius:20px;padding:2px 10px;font:12px/1.7 system-ui,sans-serif;color:var(--mut);margin:0 4px 4px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.card h3{margin:0 0 4px}
.card .meta{font:13px/1.5 system-ui,sans-serif;color:var(--mut)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0;font:14px system-ui,sans-serif}
.filters select,.filters input{padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:14px system-ui,sans-serif}
.filters input{flex:1;min-width:220px}
.ev{border-bottom:1px solid var(--line);padding:12px 0;display:grid;grid-template-columns:96px 1fr;gap:14px}
.ev time{font:14px/1.5 system-ui,sans-serif;color:var(--mut);white-space:nowrap}
.ev a{text-decoration:none;font-weight:600;color:var(--fg)}
.ev a:hover{color:var(--acc)}
.ev .meta{font:13px/1.5 system-ui,sans-serif;color:var(--mut)}
.muted{color:var(--mut)}
.small{font:13px/1.55 system-ui,sans-serif}
blockquote{border-left:3px solid var(--acc);margin:1em 0;padding:.2em 0 .2em 16px;color:var(--mut)}
.tag{display:inline-block;font:12px/1.6 system-ui,sans-serif;padding:1px 8px;border-radius:5px;background:var(--chip);margin-right:6px}
footer{border-top:1px solid var(--line);margin-top:40px;padding:20px;font:13px/1.6 system-ui,sans-serif;color:var(--mut);text-align:center}
footer p{max-width:760px;margin:0 auto}
.mapbox{border:1px solid var(--line);border-radius:10px;overflow:auto;background:#fff;max-height:78vh}
.mapbox img{display:block;min-width:1200px;width:100%}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}
@media(max-width:720px){.two{grid-template-columns:1fr}.ev{grid-template-columns:1fr}h1{font-size:27px}}
.win{color:var(--acc2);font-weight:600}
.video{position:relative;padding-top:56.25%;border-radius:8px;overflow:hidden;background:#000;margin:-2px -2px 10px;cursor:pointer}
.video iframe,.video img{position:absolute;inset:0;width:100%;height:100%;border:0;object-fit:cover}
.video .play{position:absolute;inset:0;margin:auto;width:56px;height:56px;border-radius:50%;background:rgba(0,0,0,.55);border:2px solid #fff}
.video .play::after{content:"";position:absolute;top:50%;left:54%;transform:translate(-50%,-50%);border:11px solid transparent;border-left:18px solid #fff}
.video:hover .play{background:var(--acc);border-color:var(--acc)}
.video .dur{position:absolute;right:8px;bottom:8px;background:rgba(0,0,0,.75);color:#fff;font:12px/1.6 system-ui,sans-serif;padding:1px 6px;border-radius:4px}
.day{margin:26px 0}
.day h2{position:sticky;top:52px;background:var(--bg);z-index:2}
.post{border-left:3px solid var(--line);padding:8px 0 8px 14px;margin:10px 0}
.post:hover{border-color:var(--acc)}
.post-head{font:13px/1.5 system-ui,sans-serif}
.post-head a{text-decoration:none;font-weight:600}
.post-meta{color:var(--mut);display:block}
.post-text{font:15px/1.55 system-ui,sans-serif;white-space:pre-wrap;margin:4px 0}
</style>
"""


def num(n: int) -> str:
    """Русское разделение разрядов неразрывным пробелом: 16 814, а не 16,814."""
    return f"{n:,}".replace(",", " ")


MONTHS = {"01": "января", "02": "февраля", "03": "марта", "04": "апреля",
          "05": "мая", "06": "июня", "07": "июля", "08": "августа",
          "09": "сентября", "10": "октября", "11": "ноября", "12": "декабря"}


def rusdate(iso: str) -> str:
    """2026-09-02 -> 2 сентября."""
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS.get(m, m)}"


def plural(n: int, one: str, few: str, many: str) -> str:
    """51 пост, 3 поста, 20 постов."""
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return f"{n} {one}"
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def table(counter: Counter, head: str, top: int | None = None, unit: str = "событий") -> str:
    items = counter.most_common(top)
    mx = max((v for _, v in items), default=1)
    total = sum(counter.values()) or 1
    rows = "".join(
        f"<tr><td>{E(str(k))}</td><td>{v}</td><td>{v * 100 // total}%</td>"
        f'<td style="width:44%"><i class="bar" style="width:{max(2, v * 100 // mx)}%"></i></td></tr>'
        for k, v in items
    )
    return (f'<div class="wrap"><table><tr><th>{E(head)}</th><th>{E(unit)}</th>'
            f'<th>доля</th><th></th></tr>{rows}</table></div>')


# ---------------------------------------------------------------- index
def build_index(program, exhibitors, n_books: int, n_people: int) -> str:
    evs = program["events"]
    refs = program["refs"]
    by_day = Counter(e["date"] for e in evs)
    by_venue = Counter((e["venue"]["title"] or "—") for e in evs)
    by_genre = Counter((e["genre"]["title"] or "—") for e in evs)
    by_topic = Counter((e["topic"]["title"] or "—") for e in evs)
    day_titles = {k: (refs.get(k) or {}).get("title", k) for k in by_day}
    canceled = sum(1 for e in evs if e["canceled"])
    with_desc = sum(1 for e in evs if strip_tags(e["description"]))
    hours = Counter(int((e["start"] or "0:0").split(":")[0]) for e in evs if e["start"])
    orgs = Counter(o for e in evs for o in e["organizers"])
    peak = ", ".join(f"{h}:00 — {c}" for h, c in sorted(hours.items()) if c >= max(hours.values()) * 0.8)

    return page("Разбор ярмарки в цифрах", f"""
<h1>39-я ММКЯ: из чего на самом деле состоит ярмарка</h1>
<p class="lead">2–6 сентября 2026, «Гостиный Двор». Мы выгрузили всю программу из
открытого API самой ярмарки, разобрали пресс-релиз и посчитали, что там было.</p>

<div class="stats">
  <a class="stat" href="program.html"><b>{len(evs)}</b><span>событий в программе</span></a>
  <a class="stat" href="exhibitors.html"><b>{len(exhibitors)}</b><span>участников со стендами</span></a>
  <a class="stat" href="#venues"><b>{len(by_venue)}</b><span>площадок</span></a>
  <a class="stat" href="people.html"><b>{n_people}</b><span>спикеров</span></a>
  <a class="stat" href="books.html"><b>{n_books}</b><span>книг упомянуто</span></a>
  <a class="stat" href="#organizers"><b>{len(orgs)}</b><span>организаторов событий</span></a>
</div>

<h2>Пять дней</h2>
<p>Программа распределена неравномерно: пик приходится на выходные, когда идёт массовый
посетитель, а профессиональная часть сосредоточена в первые дни.</p>
{table(Counter({day_titles[k]: v for k, v in by_day.items()}), "День")}

<h2 id="venues">Площадки</h2>
<p>13 тематических площадок в «Гостином Дворе» плюс события за его пределами —
в ЦДЛ, Электротеатре «Станиславский», отеле Four Seasons и Агентстве креативных индустрий.</p>
{table(by_venue, "Площадка")}

<h2>Жанры событий</h2>
<p>Ярмарка давно не только про презентации: заметная доля программы — лекции, дискуссии
и мастер-классы, то есть образовательный формат.</p>
{table(by_genre, "Жанр", top=15)}

<h2>Темы</h2>
{table(by_topic, "Тема")}

<h2 id="organizers">Кто держит повестку</h2>
<p>Топ организаторов по числу заявленных событий. По этому списку видно, чья это на самом
деле программа.</p>
{table(orgs, "Организатор", top=20)}

<h2>Что видно только в данных</h2>
<ul>
 <li>Описание есть у <b>{with_desc}</b> событий из {len(evs)} — раскрыто
     {with_desc * 100 // len(evs)}% программы, остальное живёт одним заголовком.</li>
 <li>Отменённых событий в выгрузке: <b>{canceled}</b>.</li>
 <li>Часы пик по числу стартующих событий: {E(peak)}.</li>
 <li>Вся программа переведена на английский и китайский — прямое следствие того,
     что почётный гость ярмарки в этом году Китай.</li>
</ul>

<h2>Куда дальше</h2>
<div class="grid">
  <div class="card"><h3><a href="program.html">Вся программа</a></h3>
    <p class="meta">{len(evs)} событий с фильтрами по дню, площадке и жанру — и отдельная страница на каждое.</p></div>
  <div class="card"><h3><a href="exhibitors.html">Участники</a></h3>
    <p class="meta">{len(exhibitors)} издательств и организаций со стендами и номерами на карте.</p></div>
  <div class="card"><h3><a href="books.html">Книги ярмарки</a></h3>
    <p class="meta">Сквозной список книг из программы со ссылками в «Дом книги».</p></div>
  <div class="card"><h3><a href="stroki.html">Строки против Литрес</a></h3>
    <p class="meta">Разбор книжного сервиса «Строки» (КИОН/МТС) и его места на рынке подписок.</p></div>
  <div class="card"><h3><a href="press.html">Пресс-релиз</a></h3>
    <p class="meta">Что организаторы обещали — и что из этого подтверждается данными программы.</p></div>
  <div class="card"><h3><a href="map.html">Карта ярмарки</a></h3>
    <p class="meta">Официальный мастерплан «Гостиного Двора».</p></div>
</div>
""", description="39-я Московская международная книжная ярмарка в цифрах: 509 событий, 243 участника, разбор программы.")


# ---------------------------------------------------------------- program
def build_program(program) -> str:
    evs = program["events"]
    refs = program["refs"]
    days = sorted({e["date"] for e in evs if e["date"]})
    day_title = {d: (refs.get(d) or {}).get("title", d) for d in days}
    venues = sorted({e["venue"]["title"] for e in evs if e["venue"]["title"]})
    genres = sorted({e["genre"]["title"] for e in evs if e["genre"]["title"]})

    def opts(items):
        return "".join(f'<option value="{E(i)}">{E(i)}</option>' for i in items)

    rows = []
    for e in evs:
        speakers = ", ".join(
            (p.get("title") if isinstance(p, dict) else str(p)) or "" for p in e["participants"][:4]
        )
        meta = E(e["venue"]["title"] or "")
        if e["genre"]["title"]:
            meta += " · " + E(e["genre"]["title"])
        if speakers:
            meta += " · " + E(speakers)
        rows.append(
            f'<div class="ev" data-day="{E(e["date"] or "")}" data-venue="{E(e["venue"]["title"] or "")}"'
            f' data-genre="{E(e["genre"]["title"] or "")}"'
            f' data-s="{E((e["title"] + " " + speakers).lower())}">'
            f'<time>{E(e["start"] or "")}–{E(e["end"] or "")}<br>'
            f'<span class="small">{E(day_title.get(e["date"], ""))}</span></time>'
            f'<div><a href="event/{E(e["id"])}.html">{E(e["title"])}</a>'
            f'<div class="meta">{meta}</div></div></div>'
        )

    daymap = json.dumps({day_title[d]: d for d in days}, ensure_ascii=False)
    script = """
<script>
const dayMap = __DAYMAP__;
const els=[...document.querySelectorAll('.ev')], cnt=document.getElementById('count');
function apply(){
  const d=dayMap[fday.value]||'', v=fvenue.value, g=fgenre.value, q=fq.value.trim().toLowerCase();
  let n=0;
  for(const el of els){
    const ok=(!d||el.dataset.day===d)&&(!v||el.dataset.venue===v)&&(!g||el.dataset.genre===g)
      &&(!q||el.dataset.s.includes(q));
    el.style.display=ok?'':'none'; if(ok)n++;
  }
  cnt.textContent='Показано '+n+' из '+els.length+' событий';
}
for(const id of ['fday','fvenue','fgenre','fq']) document.getElementById(id).addEventListener('input',apply);
apply();
</script>""".replace("__DAYMAP__", daymap)

    return page("Программа", f"""
<h1>Вся программа ярмарки</h1>
<p class="lead">{len(evs)} событий за пять дней. Фильтры работают без перезагрузки,
у каждого события своя страница с описанием, спикерами и упомянутыми книгами.</p>
<div class="filters">
  <select id="fday"><option value="">Все дни</option>{opts([day_title[d] for d in days])}</select>
  <select id="fvenue"><option value="">Все площадки</option>{opts(venues)}</select>
  <select id="fgenre"><option value="">Все жанры</option>{opts(genres)}</select>
  <input id="fq" placeholder="Поиск по названию и спикерам…">
</div>
<p class="muted small" id="count"></p>
<div id="list">{"".join(rows)}</div>
{script}
""", description=f"Полная программа ММКЯ-2026: {len(evs)} событий с фильтрами и страницей на каждое.")


# ---------------------------------------------------------------- event pages
BOOKQ = re.compile(r"«([^«»]{2,120})»")


def build_events(program, books_links, people_social, vk=None) -> int:
    vk_rec = {}                       # id события -> запись трансляции
    for v in ((vk or {}).get("videos") or []):
        if v.get("event"):
            vk_rec[v["event"]["id"]] = v
    out = SITE / "event"
    out.mkdir(parents=True, exist_ok=True)
    refs = program["refs"]
    evs = program["events"]
    idx = {e["id"]: i for i, e in enumerate(evs)}

    for e in evs:
        day = (refs.get(e["date"]) or {}).get("title", e["date"] or "")
        desc = e["description"] or '<p class="muted">Организаторы описание не дали.</p>'

        sp_html = []
        for p in e["participants"]:
            name = ((p.get("title") if isinstance(p, dict) else str(p)) or "").strip()
            if not name:
                continue
            sub = (p.get("subtitle") if isinstance(p, dict) else "") or ""
            links = social_links((people_social or {}).get(name))
            sp_html.append(
                f'<div class="card"><h3><a href="../person/{slug(name)}.html">{E(name)}</a></h3>'
                + (f'<p class="meta">{E(sub)}</p>' if sub else "")
                + (f'<p class="small">{links}</p>' if links
                   else '<p class="small muted">соцсети не нашлись</p>')
                + "</div>"
            )

        titles = {t.strip() for t in BOOKQ.findall(e["title"] + " " + strip_tags(e["description"]))}
        bk = []
        for t in sorted(titles):
            rec = (books_links or {}).get(t)
            if not rec:
                continue
            offers = " · ".join(
                f'<a href="{E(o["url"])}" rel="nofollow noopener" target="_blank">{E(o["shop"])}'
                + (f' — {E(str(o["price"]))}&nbsp;₽' if o.get("price") else "")
                + "</a>"
                for o in rec["offers"][:4]
            )
            bk.append(f'<li><b>«{E(t)}»</b>' + (" — " + offers if offers else "") + "</li>")

        links = "".join(
            f'<li><a href="{E(l if isinstance(l, str) else l.get("url", ""))}"'
            f' rel="nofollow noopener" target="_blank">'
            f'{E(l if isinstance(l, str) else (l.get("title") or l.get("url", "")))}</a></li>'
            for l in e["links"]
        )

        i = idx[e["id"]]
        prev_ = evs[i - 1] if i else None
        next_ = evs[i + 1] if i + 1 < len(evs) else None
        nav = " ".join(x for x in [
            f'<a href="{E(prev_["id"])}.html">← {E(prev_["title"][:48])}</a>' if prev_ else "",
            f'<a href="{E(next_["id"])}.html">{E(next_["title"][:48])} →</a>' if next_ else "",
        ] if x)

        tags = "".join(
            f'<span class="tag">{E(x)}</span>'
            for x in [e["genre"]["title"], e["topic"]["title"]] if x
        )
        if e["canceled"]:
            tags += '<span class="tag" style="background:#e2735f;color:#fff">отменено</span>'

        body = f"""
<p class="small"><a href="../program.html">← вся программа</a></p>
<h1>{E(e["title"])}</h1>
<p class="lead">{E(day)}, {E(e["start"] or "")}–{E(e["end"] or "")} · {E(e["venue"]["title"] or "")}</p>
<p>{tags}</p>
{desc}
{("<h2>Организаторы</h2><p>" + E(", ".join(e["organizers"])) + "</p>") if e["organizers"] else ""}
{("<h2>Участники</h2><div class='grid'>" + "".join(sp_html) + "</div>") if sp_html else ""}
{("<h2>Книги, о которых речь</h2><ul>" + "".join(bk) + "</ul>") if bk else ""}
{("<h2>Ссылки организаторов</h2><ul>" + links + "</ul>") if links else ""}
{("<h2>Запись трансляции</h2><p>Эфир этого события выложен на канале ярмарки "
  "во ВКонтакте: <b>" + E(vk_rec[e["id"]]["title"]) + "</b>"
  + (" · " + E(vk_rec[e["id"]]["duration"]) if vk_rec[e["id"]]["duration"] else "")
  + (" · " + str(vk_rec[e["id"]]["views"]) + " просмотров" if vk_rec[e["id"]]["views"] is not None else "")
  + '. <a href="https://vkvideo.ru/@mmkya/all" rel="nofollow noopener" target="_blank">Смотреть на канале</a>.</p>')
 if e["id"] in vk_rec else ""}
<h2>Первоисточник</h2>
<p><a href="{E(e["url"])}" rel="nofollow noopener" target="_blank">Это событие на официальном сайте ярмарки</a></p>
<p class="small muted">{nav}</p>
"""
        (out / f"{e['id']}.html").write_text(
            page(e["title"], body, depth=1,
                 description=(strip_tags(e["description"])[:180] or e["title"])),
            encoding="utf-8",
        )
    return len(evs)


# ---------------------------------------------------------------- exhibitors
GROUP_ORDER = [
    "Издательство", "Зарубежный участник", "Книжный магазин и дистрибуция",
    "Библиотека", "Образование и наука", "СМИ и медиа",
    "Государственная организация", "Общественная организация и фонд",
    "Цифровой сервис и технологии", "Прочее",
]


def build_exhibitors(exhibitors) -> str:
    groups = {}
    for x in exhibitors:
        groups.setdefault(x.get("group") or "Прочее", []).append(x)
    order = [g for g in GROUP_ORDER if g in groups] + [g for g in groups if g not in GROUP_ORDER]

    blocks = []
    for g in order:
        cards = []
        for x in sorted(groups[g], key=lambda i: i["name"].lower()):
            about = (x.get("about") or x.get("about_en") or "").strip()
            site = x.get("website") or ""
            if site and not site.startswith("http"):
                site = "https://" + site
            stands = ", ".join(map(str, x["stands"])) or "—"
            c = x.get("contacts") or {}
            mails = " ".join(
                f'<a href="mailto:{E(m)}">{E(m)}</a>' for m in (c.get("emails") or [])[:2])
            phones = " · ".join(E(p) for p in (c.get("phones") or [])[:2])
            soc = " ".join(
                f'<a href="{E(s["url"])}" rel="nofollow noopener" target="_blank">{E(s["network"])}</a>'
                for s in (c.get("social") or [])[:6])
            contact_html = ""
            if mails or phones or soc:
                contact_html = (
                    '<p class="small">'
                    + (f"✉ {mails}<br>" if mails else "")
                    + (f"☎ {phones}<br>" if phones else "")
                    + (soc if soc else "")
                    + "</p>"
                )
            cards.append(
                f'<div class="card" data-s="{E((x["name"] + " " + x.get("name_en", "") + " " + about).lower())}">'
                f'<h3>{E(x["name"])}</h3>'
                f'<p class="meta">Стенд {E(stands)}'
                + (f' · зона {E(x.get("zone", ""))}' if x.get("zone") and x["zone"] != "—" else "")
                + (f' · <a href="{E(site)}" rel="nofollow noopener" target="_blank">сайт</a>' if site else "")
                + "</p>"
                + (f'<p class="small">{E(about[:420])}{"…" if len(about) > 420 else ""}</p>' if about else "")
                + contact_html
                + "</div>"
            )
        blocks.append(
            f'<h2 data-group>{E(g)} <span class="muted small">— {len(groups[g])}</span></h2>'
            f'<div class="grid">{"".join(cards)}</div>'
        )

    with_about = sum(1 for x in exhibitors if x.get("about") or x.get("about_en"))
    script = """
<script>
const cards=[...document.querySelectorAll('.card[data-s]')],c=document.getElementById('c');
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();let n=0;
for(const r of cards){const ok=!v||r.dataset.s.includes(v);r.style.display=ok?'':'none';if(ok)n++;}
for(const h of document.querySelectorAll('h2[data-group]')){
  const g=h.nextElementSibling;
  const vis=[...g.children].some(e=>e.style.display!=='none');
  h.style.display=vis?'':'none'; g.style.display=vis?'':'none';
}
c.textContent='Показано '+n+' из '+cards.length;});
</script>"""
    return page("Участники", f"""
<h1>Кто стоит на ярмарке</h1>
<p class="lead">{len(exhibitors)} участников с собственными стендами, разложенных по типу
организации. Описания взяты из карточек на <a href="https://events.mibf.info/2026/expo-map"
rel="nofollow noopener" target="_blank">официальной карте ярмарки</a> — они есть
у {with_about} участников. Номера стендов совпадают с <a href="map.html">мастерпланом</a>.</p>
<div class="filters"><input id="q" placeholder="Поиск по названию и описанию…"></div>
<p class="muted small" id="c"></p>
{"".join(blocks)}
{script}
""", description=f"{len(exhibitors)} участников ММКЯ-2026 по типам организаций, с описаниями и стендами.")


# ---------------------------------------------------------------- books
def build_books(books, books_links) -> str:
    if not books:
        return page("Книги", "<h1>Книги ярмарки</h1><p>Список ещё не собран: "
                             "запустите <code>python scripts/extract_books.py</code>.</p>")
    rows = []
    for b in books:
        rec = (books_links or {}).get(b["title"], {})
        offers = rec.get("offers", [])
        shop = " · ".join(
            f'<a href="{E(o["url"])}" rel="nofollow noopener" target="_blank">{E(o["shop"])}'
            + (f' — {E(str(o["price"]))}&nbsp;₽' if o.get("price") else "")
            + "</a>"
            for o in offers[:3]
        ) or '<span class="muted">—</span>'
        where = ", ".join(
            (f'<a href="event/{E(m["event_id"])}.html">{E((m["event_title"] or "")[:52])}</a>'
             if m.get("event_id") else E(m["event_title"] or ""))
            for m in b["mentions"][:3]
        )
        rows.append(
            f'<tr data-s="{E((b["title"] + " " + b["author"]).lower())}">'
            f'<td><b>{E(b["title"])}</b>'
            + (f'<br><span class="small muted">{E(b["author"])}</span>' if b["author"] else "")
            + f'</td><td class="small">{where}</td><td class="small">{shop}</td></tr>'
        )
    withshop = sum(1 for b in books if (books_links or {}).get(b["title"], {}).get("offers"))
    script = """
<script>
const rows=[...document.querySelectorAll('tr[data-s]')],c=document.getElementById('c');
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();let n=0;
for(const r of rows){const ok=!v||r.dataset.s.includes(v);r.style.display=ok?'':'none';if(ok)n++;}
c.textContent='Показано '+n+' из '+rows.length;});
</script>"""
    return page("Книги", f"""
<h1>Книги, о которых говорили на ярмарке</h1>
<p class="lead">Сквозной список из всей программы и пресс-релиза: {len(books)} названий.
Для {withshop} из них найдены страницы в «Московском Доме книги» и других магазинах —
ссылки собраны из поисковой выдачи через XMLRiver.</p>
<div class="filters"><input id="q" placeholder="Поиск по названию или автору…"></div>
<p class="muted small" id="c"></p>
<div class="wrap"><table><tr><th>Книга</th><th>Где упоминалась</th><th>Где купить</th></tr>{"".join(rows)}</table></div>
{script}
""", description="Сквозной список книг, упомянутых на ММКЯ-2026, со ссылками где купить.")


# ---------------------------------------------------------------- people


def build_person_pages(people, social, youtube, program) -> int:
    out = SITE / "person"
    out.mkdir(parents=True, exist_ok=True)
    ev_by_id = {e["id"]: e for e in program["events"]}
    refs = program["refs"]

    for p in people:
        name = p["name"]
        s = (social or {}).get(name, {})
        vids = (youtube or {}).get(name, {}).get("videos", [])

        soc = social_links(s, limit=8)
        web = "".join(
            f'<li><a href="{E(w["url"])}" rel="nofollow noopener" target="_blank">{E(w["title"] or w["url"])}</a>'
            f'<br><span class="small muted">{E((w.get("snippet") or "")[:160])}</span></li>'
            for w in (s.get("web") or [])[:3]
        )
        vid = "".join(
            f'<li><a href="{E(v["url"])}" rel="nofollow noopener" target="_blank">{E(v["title"])}</a>'
            f'<br><span class="small muted">{E((v.get("snippet") or "")[:160])}</span></li>'
            for v in vids
        )

        evs = []
        for eid in p["events"]:
            e = ev_by_id.get(eid)
            if not e:
                continue
            day = (refs.get(e["date"]) or {}).get("title", e["date"] or "")
            evs.append(
                f'<div class="ev"><time>{E(e["start"] or "")}<br>'
                f'<span class="small">{E(day)}</span></time>'
                f'<div><a href="../event/{E(e["id"])}.html">{E(e["title"])}</a>'
                f'<div class="meta">{E(e["venue"]["title"] or "")}</div></div></div>'
            )

        role = p.get("role") or p.get("press_role") or ""
        press = ""
        if p.get("in_press"):
            press = ('<p class="tag">назван в пресс-релизе ярмарки</p>')

        body = f"""
<p class="small"><a href="../people.html">← все спикеры и авторы</a></p>
<h1>{E(name)}</h1>
{f'<p class="lead">{E(role)}</p>' if role else ""}
{press}
{f'<p>{soc}</p>' if soc else '<p class="muted small">Соцсети не нашлись.</p>'}
{("<h2>События на ярмарке</h2>" + "".join(evs)) if evs
 else '<h2>События на ярмарке</h2><p class="muted small">В программе как участник события не заявлен — упомянут в пресс-релизе.</p>'}
{("<h2>Лекции и выступления на YouTube</h2><ul>" + vid + "</ul>") if vid else ""}
{("<h2>Где ещё пишут</h2><ul>" + web + "</ul>") if web else ""}
<p class="small muted">Ссылки найдены автоматически через поисковую выдачу — возможны однофамильцы.</p>
"""
        (out / f"{slug(name)}.html").write_text(
            page(name, body, depth=1,
                 description=f"{name}{' — ' + role if role else ''}. События на ММКЯ-2026, соцсети, лекции."),
            encoding="utf-8",
        )
    return len(people)


def build_people(people, social, youtube) -> str:
    rows = []
    for p in people:
        links = social_links((social or {}).get(p["name"]), limit=4) or '<span class="muted">—</span>'
        nvid = len((youtube or {}).get(p["name"], {}).get("videos", []))
        badge = ' <span class="tag">релиз</span>' if p.get("in_press") else ""
        rows.append(
            f'<tr data-s="{E((p["name"] + " " + (p.get("role") or "")).lower())}">'
            f'<td><a href="person/{slug(p["name"])}.html"><b>{E(p["name"])}</b></a>{badge}'
            + (f'<br><span class="small muted">{E(p["role"])}</span>' if p.get("role") else "")
            + f'</td><td>{len(p["events"])}</td>'
            f'<td class="small">{links}</td>'
            f'<td class="small">{nvid or "—"}</td></tr>'
        )
    found = sum(1 for v in (social or {}).values() if v.get("social"))
    withvid = sum(1 for v in (youtube or {}).values() if v.get("videos"))
    npress = sum(1 for p in people if p.get("in_press"))
    script = """
<script>
const rows=[...document.querySelectorAll('tr[data-s]')],c=document.getElementById('c');
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();let n=0;
for(const r of rows){const ok=!v||r.dataset.s.includes(v);r.style.display=ok?'':'none';if(ok)n++;}
c.textContent='Показано '+n+' из '+rows.length;});
</script>"""
    return page("Спикеры и авторы", f"""
<h1>Спикеры и авторы ярмарки</h1>
<p class="lead">{len(people)} человек: участники событий программы плюс {npress} имён,
названных в пресс-релизе. Соцсети найдены у {found}, лекции на YouTube — у {withvid}.
У каждого своя страница.</p>
<div class="filters"><input id="q" placeholder="Поиск по имени…"></div>
<p class="muted small" id="c"></p>
<div class="wrap"><table>
<tr><th>Имя</th><th>Событий</th><th>Соцсети</th><th>Видео</th></tr>{"".join(rows)}</table></div>
{script}
""", description="Спикеры и авторы ММКЯ-2026: соцсети, события, лекции на YouTube.")


# ---------------------------------------------------------------- articles
META = re.compile(r"<!--meta(.*?)-->", re.S)


def article_meta(src: str) -> dict:
    m = META.search(src)
    if not m:
        return {}
    out = {}
    for line in m.group(1).strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def build_articles(extra: list[dict] | None = None) -> tuple[str, dict[str, str]]:
    """Читает content/articles/*.html, возвращает хаб и словарь {путь: html}."""
    files, cards = {}, []
    src_dir = CONTENT / "articles"
    entries = []
    if src_dir.exists():
        for p in sorted(src_dir.glob("*.html")):
            src = p.read_text(encoding="utf-8")
            meta = article_meta(src)
            entries.append({
                "href": f"articles/{p.stem}.html",
                "title": meta.get("title", p.stem),
                "lead": meta.get("lead", ""),
                "tag": meta.get("tag", ""),
                "body": META.sub("", src).strip(),
            })
    entries += extra or []

    for e in entries:
        if e.get("body"):
            files[e["href"]] = page(e["title"], e["body"], depth=1, description=e["lead"])
        cards.append(
            f'<div class="card"><h3><a href="{E(e["href"])}">{E(e["title"])}</a></h3>'
            + (f'<p class="meta"><span class="tag">{E(e["tag"])}</span></p>' if e.get("tag") else "")
            + (f'<p class="small">{E(e["lead"])}</p>' if e.get("lead") else "")
            + "</div>"
        )

    hub = page("Статьи", f"""
<h1>Статьи по темам ярмарки</h1>
<p class="lead">Программа ММКЯ — это не список мероприятий, а срез того, чем сейчас
живёт книжная отрасль. Мы взяли темы, которые в программе повторяются, и разобрали
каждую отдельно: что за люди, что за компании, что за книги и куда всё это движется.</p>
<div class="grid">{"".join(cards)}</div>
""", description="Разборы тем ММКЯ-2026: ИИ в редактуре, деревенская проза, книжные подкасты.")
    return hub, files


def build_rbc_biblio(data: dict) -> str:
    """Все выпуски программы «Библиотека» Радио РБК со ссылками."""
    eps = data["episodes"]
    rows = []
    for e in eps:
        date = " ".join(e["date"].split(" ")[1:4]) if e["date"] else ""
        rows.append(
            f'<tr data-s="{E((e["title"] + " " + e["description"]).lower())}">'
            f'<td class="small">{E(date)}</td>'
            f'<td><b>{E(e["title"])}</b>'
            + (f'<br><span class="small muted">{E(e["description"][:220])}</span>'
               if e["description"] else "")
            + "</td>"
            f'<td class="small">'
            + (f'<a href="{E(e["audio"])}" rel="nofollow noopener" target="_blank">слушать</a>'
               if e["audio"] else "")
            + (f' · <a href="{E(e["page"])}" rel="nofollow noopener" target="_blank">страница</a>'
               if e["page"] else "")
            + f'</td><td class="small muted">{E(e["duration"])}</td></tr>'
        )
    script = """
<script>
const rows=[...document.querySelectorAll('tr[data-s]')],c=document.getElementById('c');
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();let n=0;
for(const r of rows){const ok=!v||r.dataset.s.includes(v);r.style.display=ok?'':'none';if(ok)n++;}
c.textContent='Показано '+n+' из '+rows.length;});
</script>"""
    return page("Библиотека Радио РБК", f"""
<h1>«Библиотека» Радио РБК: все выпуски</h1>
<p class="lead">На ярмарке проект приехал <a href="../event/Hv_ZYW.html">открытым диалогом
на площадке «Чтение. Развитие»</a> — с Элиной Тихоновой и Дмитрием Брейтенбихером
из ВТБ. Сама программа выходит на Радио РБК: лидеры мнений рассказывают, какую книгу
читают прямо сейчас и почему. Здесь — все {len(eps)} выпусков со ссылками на аудио.</p>

<h2>Что это за программа</h2>
<p>Формат простой и оттого работающий: гость — руководитель компании, губернатор,
глава федерации, директор музея — приходит не рассказывать про свою отрасль,
а говорить про книгу. Литература в этой рамке становится способом узнать, как
человек принимает решения. Проект живёт не только в эфире: у него есть офлайн-встречи
(«Просто сказка» в Ленинке, «Просто детектив»), публикации на rbc.ru и подкаст.</p>
<p class="small muted">Список собран из RSS-подкаста автоматически, поэтому он полный
и обновляется пересборкой сайта. На <a href="https://biblio.rbc.ru/"
rel="nofollow noopener" target="_blank">сайте проекта</a> названия выпусков —
картинки, текстом их там нет.</p>

<h2>Выпуски</h2>
<div class="filters"><input id="q" placeholder="Поиск по гостю, книге, теме…"></div>
<p class="muted small" id="c"></p>
<div class="wrap"><table>
<tr><th>Дата</th><th>Выпуск</th><th>Слушать</th><th></th></tr>{"".join(rows)}</table></div>
{script}
<p class="small muted">Источник — официальный RSS подкаста
«<a href="{E(data.get("feed", ""))}" rel="nofollow noopener" target="_blank">Радио РБК: Библиотека</a>»,
{E(data.get("site", ""))}</p>
""", depth=1, description=f"Все {len(eps)} выпусков программы «Библиотека» Радио РБК со ссылками на аудио.")


# ---------------------------------------------------------------- telegram
FAIR_KEYS = ("ммкя", "книжная ярмарка", "гостин", "mibf")

# Каналы участников, которые к книгам отношения не имеют: общая новостная лента
# «МК» давала 284 поста за десять дней и забивала собой и ленту, и статистику.
TG_EXCLUDE = {"mk_ru"}


def tg_channels(tg: dict) -> dict:
    return {k: v for k, v in tg.items() if k not in TG_EXCLUDE}


def build_telegram(tg: dict) -> str:
    """Разбор постов телеграм-каналов участников за окно вокруг ярмарки."""
    tg = tg_channels(tg)
    posts = [(k, v["exhibitor"], p) for k, v in tg.items() for p in v["posts"]]
    fair = [(k, ex, p) for k, ex, p in posts
            if any(x in p["text"].lower() for x in FAIR_KEYS)]

    days = Counter(p["date"][:10] for _, _, p in fair)
    by_ch = Counter(k for k, _, _ in fair)
    views_by_ch = Counter()
    for k, _, p in fair:
        views_by_ch[k] += p.get("views") or 0

    themes = {
        "Номер стенда": r"стенд\s*[«\"]?[A-ZА-Я]-?\s?\d",
        "Новинка": r"новинк",
        "Детская программа": r"детск",
        "Автограф-сессия": r"автограф",
        "Скидка или промокод": r"скидк|промокод|специальн\w+ цен|издательск\w+ цен",
        "Китай": r"кита",
        "Премия «Книга года»": r"книга года|лауреат",
        "Искусственный интеллект": r"нейросет|искусственн\w+ интеллект",
    }
    theme_counts = Counter({
        name: sum(1 for _, _, p in fair if re.search(rx, p["text"], re.I))
        for name, rx in themes.items()
    })

    day_rows = "".join(
        f'<tr><td>{E(rusdate(d))}</td><td>{n}</td>'
        f'<td style="width:55%"><i class="bar" style="width:'
        f'{max(2, n * 100 // max(days.values()))}%"></i></td></tr>'
        for d, n in sorted(days.items())
    )

    ch_rows = []
    for k, n in by_ch.most_common(25):
        ex = next(e for kk, e, _ in fair if kk == k)
        ch_rows.append(
            f'<tr><td><a href="https://t.me/{E(k)}" rel="nofollow noopener" target="_blank">@{E(k)}</a>'
            f'<br><span class="small muted">{E(ex[:44])}</span></td>'
            f"<td>{n}</td><td>{num(views_by_ch[k])}</td></tr>"
        )

    top = sorted(fair, key=lambda x: -(x[2].get("views") or 0))[:20]
    top_rows = "".join(
        f'<tr><td class="small">{E(rusdate(p["date"][:10]))}</td>'
        f'<td><a href="{E(p["link"])}" rel="nofollow noopener" target="_blank">@{E(k)}</a>'
        f'<br><span class="small muted">{E(ex[:34])}</span></td>'
        f'<td class="small">{tg_html(re.sub(chr(10) + "+", " ", p["text"])[:230])}…</td>'
        f'<td>{num(p.get("views") or 0)}</td></tr>'
        for k, ex, p in top
    )

    total_views = sum(p.get("views") or 0 for _, _, p in fair)
    silent = sum(1 for v in tg.values() if not v["post_count"])
    peak_day, peak_n = max(days.items(), key=lambda x: x[1])

    return page("Телеграм участников", f"""
<h1>Что участники ярмарки писали в телеграме</h1>
<p class="lead">Мы нашли телеграм-каналы на сайтах участников и выгрузили всё, что они
опубликовали за десять дней вокруг ярмарки — с 27 августа по 6 сентября.
Получилось {plural(len(tg), "канал", "канала", "каналов")} и {plural(len(posts), "пост", "поста", "постов")}, из которых {len(fair)} —
про саму ММКЯ. Суммарно их прочитали {num(total_views)} раз.</p>

<div class="stats">
  <div class="stat"><b>{len(tg)}</b><span>каналов участников</span></div>
  <div class="stat"><b>{len(posts)}</b><span>постов за 10 дней</span></div>
  <div class="stat"><b>{len(fair)}</b><span>из них про ярмарку</span></div>
  <div class="stat"><b>{num(total_views)}</b><span>просмотров этих постов</span></div>
</div>

<h2>Издатель приходит на ярмарку торговать, а не разговаривать</h2>
<p>Самое заметное в этой выгрузке — о чём участники <b>не</b> пишут. Номер стенда
называют {plural(theme_counts["Номер стенда"], "пост", "поста", "постов")}, новинки —
{theme_counts["Новинка"]}, автограф-сессии — {theme_counts["Автограф-сессия"]},
скидки и промокоды — {theme_counts["Скидка или промокод"]}. А вот сквозные темы
самой ярмарки в постах почти отсутствуют: Китай как почётный гость упомянут
{theme_counts["Китай"]} раз, искусственный интеллект — {theme_counts["Искусственный интеллект"]}.</p>
<p>Разрыв показательный. Организаторы строят программу вокруг больших сюжетов —
международного диалога, будущего книги, ИИ. Участники используют ярмарку как
торговую точку с высоким трафиком: «стенд C-11, скидка 10%, автограф в 14:00».
Это не упрёк — просто два разных представления о том, зачем нужна ярмарка,
существующие в одном здании.</p>
{table(theme_counts, "О чём пишут", unit="постов")}

<h2>Как выглядит календарь публикаций</h2>
<p>Пик — {E(rusdate(peak_day))}, {plural(peak_n, "пост", "поста", "постов")}: день открытия. Дальше плато на все дни
работы и резкий обрыв 6 сентября, в последний день. Заметно и то, что подготовка
начинается поздно: до 31 августа про ярмарку писали единицы, основная волна
анонсов пошла за сутки-двое до открытия.</p>
<div class="wrap"><table><tr><th>День</th><th>Постов о ярмарке</th><th></th></tr>{day_rows}</table></div>

<h2>Кто громче всех</h2>
<p>По числу постов лидируют средние издательства — «КомпасГид», «Дримбук»,
«Наука». По просмотрам картина другая: десять постов «Эксмо» собрали
{num(views_by_ch["eksmo"])} просмотров — больше, чем
{plural(by_ch["kompasgid"], "пост", "поста", "постов")}
«КомпасГида». Канал самой ярмарки с {plural(by_ch["mibf_info"], "постом", "постами", "постами")} набрал
{num(views_by_ch["mibf_info"])} — меньше, чем одно крупное издательство.</p>
<p>Отдельная история — «Трендбукс»: их посты собирают по 8–14 тысяч просмотров,
это лучший результат среди участников. Молодёжная романтическая проза даёт
аудиторию, несопоставимую с академическими издательствами, у которых те же
анонсы читают 200–300 человек.</p>
<div class="wrap"><table>
<tr><th>Канал</th><th>Постов о ярмарке</th><th>Просмотров</th></tr>{"".join(ch_rows)}</table></div>

<h2>Что произошло на ярмарке по версии её участников</h2>
<ul>
  <li><b>Премия «Книга года — 2026».</b> Лауреатов объявили в Электротеатре
      «Станиславский». В «Прозе года» два победителя, среди них Сергей Шаргунов
      с романом «Попович» («Редакция Елены Шубиной»). В нон-фикшн победила книга
      Алексея Маслова «Чаепитие с драконом» («РИПОЛ классик»).</li>
  <li><b>«Слово года — 2026».</b> На Главной сцене объявили топ-40 слов-претендентов.</li>
  <li><b>Права на перевод.</b> Книгу Алисы Джукич и Каролины Харит «Фатум. Гаер»
      продали на английский, немецкий, португальский, испанский, французский
      и итальянский — редкий случай, когда о зарубежных правах сообщают прямо
      с площадки.</li>
  <li><b>Карьерная конференция «ЭКСМО-АСТ OPEN BOOK»</b> для студентов —
      издательства публично ищут кадры.</li>
  <li><b>Логистика.</b> 5 сентября перекрыли Варварку, вход перенесли на Ильинку —
      об этом канал ярмарки сообщал отдельным срочным постом.</li>
</ul>

<h2>Наблюдения, которые видно только в переписке</h2>
<p><b>Цена — главный аргумент.</b> «По ценам издательства, без торговых и
транспортных наценок» (Нигма), скидка 10% на весь стенд (ПОЛЫНЬ), промокод
на конкретную книгу (РИПОЛ классик). Для читателя ярмарка — это в первую очередь
возможность купить дешевле, и издатели это прямо эксплуатируют.</p>
<p><b>Книги везут из типографии прямо на стенд.</b> Минимум два издательства
сообщили, что новинка поступит в продажу только завтра, а на ярмарке её можно
купить уже сегодня. Ярмарка работает как канал первой продажи, а не как витрина.</p>
<p><b>Четверг — провальный день.</b> «РИПОЛ классик» написали прямо: «по четвергам
на книжные выставки никто не ходит… и зря, потому что нет толп, издатели ещё не
замученные, и все книги в наличии». Это совпадает с распределением программы,
где выходные перегружены, а первые дни отданы профессионалам.</p>
<p><b>Каналы молчат чаще, чем говорят.</b> Из {len(tg)} найденных каналов
{plural(silent, "не опубликовал", "не опубликовали", "не опубликовали")}
за десять дней ничего. Телеграм у издательства
формально есть, но живым каналом его назвать нельзя.</p>

<h2>Самые читаемые посты о ярмарке</h2>
<div class="wrap"><table>
<tr><th>Дата</th><th>Канал</th><th>Пост</th><th>Просмотров</th></tr>{top_rows}</table></div>

<p class="small muted">Каналы найдены автоматически на сайтах участников
(скилл <code>contact-scraper</code>), посты выгружены через Telegram API за период
27 августа — 6 сентября 2026. Цитаты приведены со ссылкой на исходное сообщение.
Здесь только публичные каналы организаций-участников; личные переписки
и закрытые чаты не затрагиваются.</p>
""", description="Разбор постов телеграм-каналов участников ММКЯ-2026 за 10 дней вокруг ярмарки.")


def build_tg_feed(tg: dict) -> str:
    """Все посты каналов участников одной лентой, разбитой по дням."""
    tg = tg_channels(tg)
    posts = []
    for k, v in tg.items():
        for p in v["posts"]:
            posts.append({
                "channel": k,
                "exhibitor": v["exhibitor"],
                "group": v.get("group") or "Прочее",
                **p,
            })
    posts.sort(key=lambda p: p["date"], reverse=True)

    groups = sorted({p["group"] for p in posts})
    channels = sorted({p["channel"] for p in posts}, key=str.lower)

    by_day: dict[str, list[dict]] = {}
    for p in posts:
        by_day.setdefault(p["date"][:10], []).append(p)

    blocks = []
    for day in sorted(by_day, reverse=True):
        items = by_day[day]
        cards = []
        for p in items:
            text = p["text"].strip()
            cut = text[:600] + ("…" if len(text) > 600 else "")
            fair = any(x in text.lower() for x in FAIR_KEYS)
            cards.append(
                f'<div class="post" data-group="{E(p["group"])}" data-ch="{E(p["channel"])}"'
                f' data-fair="{"1" if fair else "0"}"'
                f' data-s="{E((p["exhibitor"] + " " + text[:300]).lower())}">'
                f'<div class="post-head">'
                f'<a href="https://t.me/{E(p["channel"])}" rel="nofollow noopener" target="_blank">'
                f'@{E(p["channel"])}</a>'
                f'<span class="muted"> · {E(p["exhibitor"][:46])}</span>'
                f'<span class="post-meta">{E(p["date"][11:16])}'
                + (f' · {num(p["views"])} просм.' if p.get("views") else "")
                + f' · <a href="{E(p["link"])}" rel="nofollow noopener" target="_blank">пост</a></span>'
                f"</div>"
                f'<div class="post-text">{tg_html(cut)}</div>'
                + ('<span class="tag">про ярмарку</span>' if fair else "")
                + "</div>"
            )
        blocks.append(
            f'<section class="day" data-day="{E(day)}">'
            f'<h2>{E(rusdate(day))} <span class="muted small">— '
            f'{plural(len(items), "пост", "поста", "постов")}</span></h2>'
            f'{"".join(cards)}</section>'
        )

    def opts(items):
        return "".join(f'<option value="{E(i)}">{E(i)}</option>' for i in items)

    script = """
<script>
const posts=[...document.querySelectorAll('.post')],
      days=[...document.querySelectorAll('.day')],
      c=document.getElementById('c');
function apply(){
  const g=fgroup.value, ch=fch.value, only=fonly.checked, q=fq.value.trim().toLowerCase();
  let n=0;
  for(const p of posts){
    const ok=(!g||p.dataset.group===g)&&(!ch||p.dataset.ch===ch)
      &&(!only||p.dataset.fair==='1')&&(!q||p.dataset.s.includes(q));
    p.style.display=ok?'':'none'; if(ok)n++;
  }
  for(const d of days){
    const vis=[...d.querySelectorAll('.post')].some(e=>e.style.display!=='none');
    d.style.display=vis?'':'none';
  }
  c.textContent='Показано '+n+' из '+posts.length+' постов';
}
for(const id of ['fgroup','fch','fq']) document.getElementById(id).addEventListener('input',apply);
fonly.addEventListener('change',apply);
apply();
</script>"""

    first, last = min(by_day), max(by_day)
    return page("Лента", f"""
<h1>Лента телеграм-каналов участников</h1>
<p class="lead">Всё, что издательства и другие участники ярмарки опубликовали
с {E(rusdate(first))} по {E(rusdate(last))} — {plural(len(posts), "пост", "поста", "постов")}
из {plural(len(tg), "канала", "каналов", "каналов")}, одной лентой от свежих к старым.
Разбор этой выгрузки — на странице <a href="telegram.html">«Телеграм»</a>.</p>

<div class="filters">
  <select id="fgroup"><option value="">Все типы участников</option>{opts(groups)}</select>
  <select id="fch"><option value="">Все каналы</option>{opts(channels)}</select>
  <input id="fq" placeholder="Поиск по тексту поста…">
  <label class="small" style="align-self:center">
    <input type="checkbox" id="fonly"> только про ярмарку</label>
</div>
<p class="muted small" id="c"></p>
{"".join(blocks)}
{script}
""", description="Лента постов телеграм-каналов участников ММКЯ-2026 по дням.")


# ---------------------------------------------------------------- static pages
def build_from_content(name: str, title: str, description: str = "") -> str | None:
    p = CONTENT / name
    if not p.exists():
        return None
    return page(title, p.read_text(encoding="utf-8"), description=description)


def build_map() -> str:
    return page("Карта", """
<h1>Мастерплан «Гостиного Двора»</h1>
<p class="lead">Официальная схема ярмарки: 13 тематических площадок и стенды участников.
Схема векторная и очень широкая (16 158 px), поэтому её удобнее тянуть мышью.</p>
<div class="mapbox"><img src="assets/masterplan.svg" alt="Мастерплан ММКЯ-2026" loading="lazy"></div>
<p class="small muted">Источник — официальный SVG ярмарки. Подписи в файле переведены в кривые,
поэтому текстом названия участников оттуда не читаются: номера стендов смотрите
в <a href="exhibitors.html">списке участников</a>.</p>
""", description="Карта ММКЯ-2026: мастерплан «Гостиного Двора».")


def build_video(vk: dict | None) -> str:
    if vk and vk.get("videos"):
        vids = vk["videos"]
        rows = []
        for v in vids:
            ev = v.get("event")
            where = (f'<a href="event/{E(ev["id"])}.html">{E(ev["title"][:60])}</a>'
                     f'<br><span class="small muted">{E(ev["day"])} · {E(ev["venue"] or "")}</span>'
                     if ev else '<span class="muted">нет в программе</span>')
            rows.append(
                f'<tr data-s="{E(v["title"].lower())}">'
                f'<td><b>{E(v["title"])}</b>'
                + (f'<br><span class="small muted">{E(v["duration"])}</span>' if v["duration"] else "")
                + f'</td><td>{v["views"] if v["views"] is not None else "—"}</td>'
                f'<td class="small">{where}</td>'
                + (f'<td class="small"><a href="{E(v["url"])}" rel="nofollow noopener" '
                   'target="_blank">ВК</a></td>' if v.get("url") else '<td>—</td>')
                + "</tr>"
            )
        # плееры: ссылка с hash берётся из VK API, см. import_vk_videos.embed_url
        players = []
        for v in sorted((x for x in vids if x.get("embed")),
                        key=lambda x: -(x["views"] or 0)):
            ev = v.get("event")
            # превью с кликом: 40 сторонних фреймов на одной странице — это долго
            # и тяжело, поэтому фрейм подставляется только по нажатию
            thumb = (f'<img src="{E(v["thumb"])}" alt="" loading="lazy">'
                     if v.get("thumb") else "")
            players.append(
                '<div class="card">'
                f'<div class="video" data-embed="{E(v["embed"], quote=True)}" '
                f'data-url="{E(v["url"], quote=True)}" '
                f'role="button" tabindex="0" '
                f'aria-label="Смотреть: {E(v["title"], quote=True)}">'
                f'{thumb}<span class="play"></span>'
                + (f'<span class="dur">{E(v["duration"])}</span>' if v.get("duration") else "")
                + '</div>'
                f'<h3>{E(v["title"])}</h3>'
                f'<p class="meta">{E(v["duration"])}'
                + (f' · {num(v["views"])} просмотров' if v["views"] else "")
                + (f' · {E(rusdate(v["date"]))}' if v.get("date") else "")
                + "</p>"
                '<p class="small">'
                + (f'<a href="{E(v["url"])}" rel="nofollow noopener" target="_blank">'
                   "смотреть во ВКонтакте</a>" if v.get("url") else "")
                + (f' · <a href="event/{E(ev["id"])}.html">анонс события</a>' if ev else "")
                + "</p></div>"
            )
        play_script = """
<script>
// Превью -> плеер по клику: iframe создаётся только для нажатой записи.
// VK не отдаёт плеер в iframe с незащищённого origin (проверено: с http://127.0.0.1
// показывает «Видео недоступно», с https тот же код играет), поэтому при локальном
// просмотре открываем запись во ВКонтакте вместо мёртвого фрейма.
const canEmbed = location.protocol === 'https:';
for (const box of document.querySelectorAll('.video[data-embed]')) {
  const open = () => {
    if (!canEmbed) { window.open(box.dataset.url, '_blank', 'noopener'); return; }
    const f = document.createElement('iframe');
    f.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture';
    f.allowFullscreen = true;
    f.src = box.dataset.embed + '&autoplay=1';
    box.replaceChildren(f);
    box.removeAttribute('role');
    box.style.cursor = 'default';
  };
  box.addEventListener('click', open);
  box.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
  });
}
if (!canEmbed) {
  const n = document.getElementById('embed-note');
  if (n) n.hidden = false;
}
</script>"""

        players_html = ""
        if players:
            players_html = (
                "<h2>Смотреть здесь</h2>"
                "<p>Нажмите на превью — запись откроется прямо здесь, во встроенном "
                "плеере VK. Порядок — по числу просмотров.</p>"
                '<p class="small muted" id="embed-note" hidden>Страница открыта по http, '
                "а VK отдаёт плеер только защищённым страницам — поэтому клик открывает "
                "запись во ВКонтакте. На опубликованном сайте (https) видео играет здесь.</p>"
                f'<div class="grid">{"".join(players)}</div>' + play_script
            )

        top = max(vids, key=lambda v: v["views"] or 0)
        total = sum(v["views"] or 0 for v in vids)
        script = """
<script>
const rows=[...document.querySelectorAll('tr[data-s]')],c=document.getElementById('c');
q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();let n=0;
for(const r of rows){const ok=!v||r.dataset.s.includes(v);r.style.display=ok?'':'none';if(ok)n++;}
c.textContent='Показано '+n+' из '+rows.length;});
</script>"""
        body = f"""
<h1>Записи трансляций ярмарки</h1>
<p class="lead">ВКонтакте — официальная соцсеть и партнёр трансляций ММКЯ-2026: эфиры
велись с Главной сцены и с площадки «Будущее книги». На канале ярмарки выложено
{len(vids)} записей, {vk["matched"]} из них мы сопоставили с событиями программы —
у каждой можно открыть анонс, описание и список участников.</p>

<div class="stats">
  <div class="stat"><b>{len(vids)}</b><span>записей на канале</span></div>
  <div class="stat"><b>{num(total)}</b><span>просмотров суммарно</span></div>
  <div class="stat"><b>{vk["matched"]}</b><span>привязаны к программе</span></div>
</div>

<h2>Что смотрят</h2>
<p>Разброс просмотров говорит о ярмарке больше, чем расписание. Абсолютный лидер —
<b>«{E(top["title"])}»</b> ({num(top["views"])} просмотров): профессиональная дискуссия
об ИИ собирает аудиторию на порядок большую, чем встречи с известными авторами.
Следом идут открытие ярмарки и разговор о книжном рынке. Презентации отдельных
книг, даже у популярных писателей, держатся в районе сотни просмотров.</p>
<p>Вывод неприятный для издателей, но полезный: онлайн-аудитория ярмарки приходит
не за автографом, а за отраслевым разговором.</p>

{players_html}

<h2>Все записи</h2>
<div class="filters"><input id="q" placeholder="Поиск по названию…"></div>
<p class="muted small" id="c"></p>
<div class="wrap"><table>
<tr><th>Запись</th><th>Просмотров</th><th>Событие программы</th><th></th></tr>{"".join(rows)}</table></div>
{script}

<h2>Где смотреть</h2>
<div class="grid">
  <div class="card"><h3><a href="{E(vk["channel"])}" target="_blank" rel="noopener">VK Видео — канал ярмарки</a></h3>
    <p class="meta">Все записи трансляций.</p></div>
  <div class="card"><h3><a href="https://vk.com/mmkya" target="_blank" rel="noopener">Сообщество ВКонтакте</a></h3>
    <p class="meta">Анонсы, репортажи, клипы.</p></div>
  <div class="card"><h3><a href="https://t.me/mibf_info" target="_blank" rel="noopener">Телеграм ярмарки</a></h3>
    <p class="meta">Оперативные новости площадок.</p></div>
  <div class="card"><h3>#прокниги в VK Клипах</h3>
    <p class="meta">Запущенный к ярмарке тренд: подборки и рассказы о любимых книгах.</p></div>
</div>

<p class="small muted">Список роликов и ссылки плееров получены методом
<code>video.get</code> VK API прямо в браузере пользователя
(<code>scripts/vk_grab_api.py</code> через скилл <code>browser-bridge</code>):
страница канала без авторизации отдаёт редирект на <code>errorCode=11300</code>,
а плеер <code>video_ext.php</code> без параметра <code>hash</code> пишет
«Видео недоступно». Токен при этом остаётся в браузере и наружу не уходит.
Данные на {E(vk.get("fetched", ""))}.</p>
"""
        return page("Видео", body,
                    description=f"{len(vids)} записей трансляций ММКЯ-2026, привязанных к программе.")

    return page("Видео", """
<h1>Видео и трансляции ярмарки</h1>
<p class="lead">ВКонтакте — официальная соцсеть и партнёр трансляций ММКЯ-2026.
В этом году прямые эфиры велись только с Главной сцены.</p>
<div class="grid">
  <div class="card"><h3><a href="https://vkvideo.ru/@mmkya" target="_blank" rel="noopener">VK Видео — канал ярмарки</a></h3>
    <p class="meta">Записи выступлений и трансляций с Главной сцены.</p></div>
  <div class="card"><h3><a href="https://vk.com/mmkya" target="_blank" rel="noopener">Сообщество ВКонтакте</a></h3>
    <p class="meta">Анонсы, репортажи, клипы.</p></div>
  <div class="card"><h3><a href="https://t.me/mibf_info" target="_blank" rel="noopener">Телеграм ярмарки</a></h3>
    <p class="meta">Оперативные новости площадок.</p></div>
  <div class="card"><h3>#прокниги в VK Клипах</h3>
    <p class="meta">Запущенный к ярмарке тренд: подборки и рассказы о любимых книгах.</p></div>
</div>
<h2>Почему списка роликов здесь пока нет</h2>
<p>Страница <code>vkvideo.ru/@mmkya</code> отдаёт редирект и рендерится скриптами — одним
HTTP-запросом список роликов оттуда не забрать. Рабочий путь — метод <code>video.get</code>
VK API с сервисным токеном: он вернёт названия, длительность, просмотры и даты всех роликов
сообщества, после чего страница со списком соберётся так же, как программа.
Токен кладётся в <code>.env</code> как <code>VK_SERVICE_TOKEN</code>.</p>
""", description="Видео и трансляции ММКЯ-2026: VK Видео, Телеграм, клипы.")


# ---------------------------------------------------------------- main
def main() -> None:
    program = load("program.json")
    if not program:
        raise SystemExit("Нет data/program.json — сначала: python scripts/fetch_all.py")
    exhibitors = (load("exhibitors.json") or {}).get("exhibitors", [])
    books = (load("books.json") or {}).get("books", [])
    books_links = load("books_links.json", {})
    people = (load("people.json") or {}).get("people", [])
    social = load("people_social.json", {})
    youtube = load("people_youtube.json", {})
    rbc = load("rbc_biblio.json")
    vk = load("vk_videos.json")
    tg = load("tg_posts.json")

    global CSS_VER
    css = CSS.replace("</style>", "").strip()
    CSS_VER = hashlib.sha1(css.encode("utf-8")).hexdigest()[:8]
    (SITE / "assets").mkdir(parents=True, exist_ok=True)
    (SITE / "assets" / "style.css").write_text(css, encoding="utf-8")

    pages = {
        "index.html": build_index(program, exhibitors, len(books), len(people)),
        "program.html": build_program(program),
        "exhibitors.html": build_exhibitors(exhibitors),
        "books.html": build_books(books, books_links),
        "people.html": build_people(people, social, youtube),
        "map.html": build_map(),
        "video.html": build_video(vk),
    }
    if tg:
        pages["telegram.html"] = build_telegram(tg)
        pages["tg-feed.html"] = build_tg_feed(tg)

    for fn, title, desc in [
        ("press.html", "Пресс-релиз", "Разбор официального пресс-релиза ММКЯ-2026."),
        ("stroki.html", "Строки vs Литрес",
         "«Строки» (КИОН/МТС) против Литрес, Яндекс Книг и других книжных подписок."),
    ]:
        got = build_from_content(fn, title, desc)
        if got:
            pages[fn] = got

    # статьи: авторские из content/articles + сгенерированные из данных
    extra = []
    if rbc:
        extra.append({
            "href": "articles/rbc-biblioteka.html",
            "title": "«Библиотека» Радио РБК: все выпуски",
            "lead": f'Все {rbc["count"]} выпусков программы со ссылками на аудио — '
                    "проект, который приехал на ярмарку отдельным событием.",
            "tag": "Медиа",
            "body": None,
        })
    hub, article_files = build_articles(extra)
    pages["articles.html"] = hub
    if rbc:
        article_files["articles/rbc-biblioteka.html"] = build_rbc_biblio(rbc)

    for name, doc in {**pages, **article_files}.items():
        (SITE / name).parent.mkdir(parents=True, exist_ok=True)
        (SITE / name).write_text(doc, encoding="utf-8")

    n = build_events(program, books_links, social, vk)
    np_ = build_person_pages(people, social, youtube, program)

    for src, dst in [
        (DATA / "raw" / "masterplan.svg", SITE / "assets" / "masterplan.svg"),
        (DATA / "press" / "press-release.pdf", SITE / "assets" / "press-release.pdf"),
    ]:
        if src.exists():
            shutil.copy(src, dst)

    print(f"Сайт собран: {len(pages)} страниц + {len(article_files)} статей "
          f"+ {n} событий + {np_} персон -> {SITE}")


if __name__ == "__main__":
    main()
