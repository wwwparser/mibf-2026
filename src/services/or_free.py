"""Бесплатные модели OpenRouter + резервный провайдер. Автоподбор и ротация.

Самодостаточный модуль — копируется в проект как `src/llm.py` или импортируется
отсюда. Зависимостей нет: только стандартная библиотека и `curl` в PATH.

    from or_free import chat, chat_json, probe, free_models

CLI:
    python or_free.py probe          # что живо прямо сейчас
    python or_free.py models         # очередь моделей по порядку попыток
    python or_free.py ask "вопрос"   # разовый запрос


Порядок такой:
  1. **OpenRouter, бесплатные модели** — основной путь, платить не надо.
     Список тянется живьём и фильтруется по нулевой цене.
  2. **AgentRouter** — резерв на случай, когда бесплатные разом в лимитах
     (`deepseek-v4-flash`, `glm-5.3`, `gpt-5.6-sol`).

Три особенности, из-за которых код выглядит именно так:

1. **Транспорт — curl, а не requests.** WAF OpenRouter режет `requests` по
   TLS-отпечатку: на любой запрос приходит 403 "Access denied by security policy",
   независимо от заголовков и ключа. curl проходит. Проверено 04.09.2026.

2. **Бесплатные модели постоянно «моргают».** На один и тот же запрос модель
   отдаёт то 200, то 429 (общий лимит провайдера), то 403 (модель открыли только
   платному тиру). Поэтому одной модели быть не может: модели пробуются по
   очереди, упавшая уходит в «отдых» на cooldown.

3. **Список бесплатных моделей обновляется сам** — новые появляются, старые
   становятся платными, и хардкод устарел бы через месяц. Ручной рейтинг
   (PREFERRED) только задаёт порядок предпочтения среди реально бесплатных.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time

import sys
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

OPENROUTER = "https://openrouter.ai/api/v1"

# Кэши. Переопредели OR_CACHE_DIR, если хочешь держать их внутри проекта.
CACHE_DIR = Path(os.getenv("OR_CACHE_DIR", Path.home() / ".cache" / "openrouter-free"))
MODELS_CACHE = CACHE_DIR / "models.json"
HEALTH = CACHE_DIR / "model_health.json"
CACHE_TTL = 6 * 3600          # список моделей меняется не каждый час
COOLDOWN = 900                # упавшая по лимиту модель отдыхает 15 мин

# Порядок предпочтения среди бесплатных OpenRouter. Первые — те, что лучше
# держат русский текст и строгий JSON. Модели не из списка идут после, по
# размеру контекста. openrouter/free — роутер, сам выбирает живую бесплатную:
# держим последним как страховку, когда всё остальное в лимитах.
PREFERRED = [
    "z-ai/glm-5.2:free",
    "minimax/minimax-m3:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "thinkingmachines/inkling:free",
    "google/gemma-4-31b-it:free",
    "minimax/minimax-m2.7:free",
    "dots-studio/dots-3-note-preview:free",
    "inclusionai/ling-3.0-flash-fin:free",
    "google/gemma-4-26b-a4b-it:free",
    "cohere/north-mini-code:free",
    "openrouter/free",
]

# Бесплатные, но не для текста: музыка, классификаторы, эмбеддинги, TTS,
# плюс те, что льют цепочку рассуждений прямо в ответ вместо результата.
EXCLUDE_SUBSTRINGS = ("lyria", "content-safety", "guard", "embed", "tts",
                      "whisper", "-image", "moderation", "rerank",
                      "nemotron-3-super", "nemotron-3.5-lightning", "-reasoning")
MIN_CONTEXT = 60000           # транскрипт часового видео — это десятки тысяч токенов

# Резерв. Замер 04.09.2026: deepseek-v4-flash отвечает за 1.5-4 с и лучше всех
# держит русский; claude-opus-5 и claude-opus-4-8 отдают 402 «Budget pool quota
# has been exhausted», поэтому в списке их нет.
AGENTROUTER_MODELS = ["deepseek-v4-flash", "glm-5.3", "gpt-5.6-sol"]


class LLMError(RuntimeError):
    pass


# ------------------------------------------------------------ транспорт ----
def _secret(name: str) -> str | None:
    """Ключ из окружения, иначе из общего файла ключей."""
    v = os.getenv(name)
    if v:
        return v
    f = Path.home() / ".claude" / "secrets" / "api-keys.env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _openrouter_key() -> str | None:
    return _secret("OPENROUTER_API_KEY")


def _agentrouter() -> tuple[str, str, str] | None:
    """(base, key, user-agent) резервного провайдера или None, если не настроен.

    User-Agent обязателен: с дефолтным curl-овским AgentRouter отвечает отказом.
    """
    key = _secret("AGENTROUTER_API_KEY")
    if not key:
        return None
    return (_secret("AGENTROUTER_BASE_URL") or "https://agentrouter.org/v1", key,
            _secret("AGENTROUTER_USER_AGENT") or "claude-cli/1.0.0 (external, cli)")


def _endpoint(provider: str) -> tuple[str, str, str]:
    if provider == "openrouter":
        key = _openrouter_key()
        if not key:
            raise LLMError("OpenRouter не настроен")
        return OPENROUTER, key, UA
    ar = _agentrouter()
    if not ar:
        raise LLMError("AgentRouter не настроен")
    return ar


def _curl(base: str, path: str, key: str, ua: str, body: dict | None = None,
          timeout: int = 240) -> tuple[int, str]:
    cmd = ["curl", "-sS", "-o", "-", "-w", "\n%{http_code}", "--max-time", str(timeout),
           f"{base}{path}",
           "-H", f"Authorization: Bearer {key}",
           "-H", "Content-Type: application/json",
           "-H", "Accept: application/json",
           "-H", f"User-Agent: {ua}"]
    if body is not None:
        cmd += ["-X", "POST", "--data-binary", "@-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 30,
                           input=json.dumps(body).encode("utf-8") if body else None)
    except subprocess.TimeoutExpired:
        return 0, "таймаут curl"
    out = r.stdout.decode("utf-8", "replace")
    text, _, code = out.rpartition("\n")
    return (int(code) if code.strip().isdigit() else 0), text


def _parse(text: str) -> dict:
    """OpenRouter шлёт keep-alive пустые строки перед JSON — их надо срезать."""
    text = text.strip()
    if not text:
        raise LLMError("пустой ответ")
    i = text.find("{")
    if i < 0:
        raise LLMError(f"ответ не JSON: {text[:200]}")
    return json.loads(text[i:])


def _content(d: dict) -> str:
    """Текст ответа. Reasoning-модели кладут в `content` null (рассуждение — в
    `reasoning`); такой ответ нам не подходит, уйдём к следующей модели."""
    msg = ((d.get("choices") or [{}])[0] or {}).get("message") or {}
    return (msg.get("content") or "").strip()


# ------------------------------------------------------- список моделей ----
def _fetch_models(force: bool = False) -> list[dict]:
    if not force and MODELS_CACHE.exists() and \
            time.time() - MODELS_CACHE.stat().st_mtime < CACHE_TTL:
        return json.loads(MODELS_CACHE.read_text(encoding="utf-8"))["data"]
    code, text = _curl(OPENROUTER, "/models", _openrouter_key() or "", UA, timeout=90)
    if code != 200:
        if MODELS_CACHE.exists():          # сеть подвела — работаем по старому списку
            return json.loads(MODELS_CACHE.read_text(encoding="utf-8"))["data"]
        raise LLMError(f"не удалось получить список моделей: {code} {text[:200]}")
    MODELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_CACHE.write_text(text, encoding="utf-8")
    return _parse(text)["data"]


def free_models(force: bool = False) -> list[str]:
    """Бесплатные текстовые модели OpenRouter, в порядке предпочтения."""
    out = []
    for m in _fetch_models(force):
        pr = m.get("pricing") or {}
        try:
            if float(pr.get("prompt", 1)) != 0 or float(pr.get("completion", 1)) != 0:
                continue
        except (TypeError, ValueError):
            continue
        mid = m["id"]
        if any(s in mid for s in EXCLUDE_SUBSTRINGS):
            continue
        if (m.get("context_length") or 0) < MIN_CONTEXT:
            continue
        out.append((mid, m.get("context_length") or 0))

    def rank(item: tuple[str, int]) -> tuple[int, int]:
        mid, ctx = item
        return (PREFERRED.index(mid) if mid in PREFERRED else len(PREFERRED), -ctx)

    return [mid for mid, _ in sorted(out, key=rank)]


def providers_queue(force: bool = False) -> list[tuple[str, str]]:
    """Очередь попыток: [(провайдер, модель), ...]. Резерв — в самом конце.

    AgentRouter платный и с общей квотой, поэтому идёт только после того, как
    все бесплатные отказали. Нет ключа — просто не добавляется.
    """
    q: list[tuple[str, str]] = []
    if _openrouter_key():
        try:
            q += [("openrouter", m) for m in free_models(force)]
        except (LLMError, json.JSONDecodeError, KeyError) as e:
            # Именно тот случай, ради которого резерв и заводился: OpenRouter
            # лежит целиком, список моделей не приходит. Падать тут нельзя —
            # иначе до резерва дело не дойдёт.
            print(f"[llm] список моделей OpenRouter недоступен ({e}), "
                  f"иду сразу в резерв")
    if _agentrouter():
        q += [("agentrouter", m) for m in AGENTROUTER_MODELS]
    if not q:
        raise SystemExit("Не задан ни OPENROUTER_API_KEY, ни AGENTROUTER_API_KEY "
                         "в .env (см. README).")
    return q


# ------------------------------------------------- здоровье и ротация ----
def _health() -> dict:
    if HEALTH.exists():
        try:
            return json.loads(HEALTH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _mark(tag: str, ok: bool, note: str = "") -> None:
    h = _health()
    rec = h.setdefault(tag, {"ok": 0, "fail": 0, "cooldown_until": 0, "note": ""})
    if ok:
        rec["ok"] += 1
        rec["cooldown_until"] = 0
    else:
        rec["fail"] += 1
        rec["cooldown_until"] = int(time.time()) + COOLDOWN
        rec["note"] = note[:120]
    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")


def _available(queue: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Отдыхающие уходят в конец, но порядок ПРОВАЙДЕРОВ сохраняется: платный
    резерв не должен всплыть вперёд бесплатных только потому, что те в cooldown.
    """
    h, now = _health(), time.time()

    def fresh(item: tuple[str, str]) -> bool:
        return h.get(f"{item[0]}:{item[1]}", {}).get("cooldown_until", 0) <= now

    main = [i for i in queue if i[0] == "openrouter"]
    back = [i for i in queue if i[0] != "openrouter"]
    return ([i for i in main if fresh(i)] + [i for i in main if not fresh(i)]
            + [i for i in back if fresh(i)] + [i for i in back if not fresh(i)])


# ---------------------------------------------------------------- вызов ----
def chat(system: str, user: str, *, json_mode: bool = False,
         max_tokens: int = 2000, temperature: float = 0.3,
         attempts_per_model: int = 2) -> str:
    queue = _available(providers_queue())
    if not queue:
        raise LLMError("не нашлось ни одной доступной модели")

    errors: list[str] = []
    for provider, model in queue:
        base, key, ua = _endpoint(provider)
        tag = f"{provider}:{model}"

        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        for attempt in range(attempts_per_model):
            code, text = _curl(base, "/chat/completions", key, ua, body)
            if code == 200:
                try:
                    content = _content(_parse(text))
                except (LLMError, json.JSONDecodeError, IndexError) as e:
                    errors.append(f"{tag}: битый ответ ({e})")
                    break
                if content:
                    _mark(tag, True)
                    if provider != "openrouter":
                        print(f"[llm] бесплатные не ответили, взял резерв: {tag}")
                    return content
                _mark(tag, False, "пустой content (reasoning-модель)")
                errors.append(f"{tag}: пустой content")
                break
            if code == 429:                    # общий лимит провайдера
                if attempt + 1 < attempts_per_model:
                    time.sleep(3)
                    continue
                _mark(tag, False, "429 лимит")
                errors.append(f"{tag}: 429")
                break
            if code in (401, 402, 403, 404):   # ключ/квота/тир — повтор не поможет
                _mark(tag, False, str(code))
                errors.append(f"{tag}: {code}")
                break
            time.sleep(2 * (attempt + 1))      # 5xx/сеть
            if attempt + 1 == attempts_per_model:
                _mark(tag, False, str(code))
                errors.append(f"{tag}: {code} {text[:80]}")

    raise LLMError("все модели отказали: " + "; ".join(errors[:10]))


def _strip_fences(raw: str) -> str:
    """Снять markdown-обёртку. Модели любят завернуть JSON в ```json ... ```
    даже при response_format=json_object — сам ответ валиден, но json.loads
    на нём падает."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def chat_json(system: str, user: str, *, attempts: int = 3, **kw) -> dict:
    """Ответ с разбором JSON.

    Повтор нужен не для сети, а для самих моделей: ответ приходит то в
    markdown-обёртке, то обрезанным по лимиту токенов (тогда закрывающей скобки
    просто нет). Упавшая модель уходит в cooldown, и следующая попытка идёт уже
    к другой — обычно этого хватает.
    """
    last = ""
    for i in range(attempts):
        raw = chat(system, user, json_mode=True, **kw)
        s = _strip_fences(raw)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(s[a:b + 1])
            except json.JSONDecodeError:
                pass
        last = raw[:200]
        if i + 1 < attempts:
            print(f"[llm] ответ не разобрался как JSON, пробую другую модель "
                  f"({i + 1}/{attempts})")
    raise LLMError(f"модель вернула не JSON после {attempts} попыток: {last}")


def probe(verbose: bool = True) -> list[tuple[str, str]]:
    """Прогнать все модели коротким запросом — что живо прямо сейчас."""
    res = []
    for provider, model in providers_queue(force=True):
        base, key, ua = _endpoint(provider)
        tag = f"{provider}:{model}"
        code, text = _curl(base, "/chat/completions", key, ua, {
            "model": model,
            "messages": [{"role": "user",
                          "content": "Ответь одним словом по-русски: столица Франции?"}],
            # Лимит намеренно щедрый: reasoning-модели тратят токены на
            # размышление и с max_tokens=30 отдают пустой content — проверка
            # была бы нечестной и забраковала бы рабочие модели.
            "max_tokens": 800})
        if code == 200:
            try:
                ans = _content(_parse(text))
            except (LLMError, json.JSONDecodeError, IndexError):
                ans = ""
            status, ok = ((f"OK  {ans[:44]}", True) if ans
                          else ("пустой content (reasoning-модель)", False))
        else:
            status, ok = str(code), False
        _mark(tag, ok)
        res.append((tag, status))
        if verbose:
            print(f"{tag:<58} {status}")
    return res


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "probe":
        probe()
    elif cmd == "models":
        for provider, model in providers_queue(force=True):
            print(f"{provider:<12} {model}")
    elif cmd == "ask":
        if len(sys.argv) < 3:
            print("укажи вопрос")
            return 1
        print(chat("Ты полезный ассистент. Отвечай по-русски.", sys.argv[2]))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
