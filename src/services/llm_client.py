"""Дешёвая LLM для механической работы над данными (извлечение полей,
классификация, нормализация JSON). Тексты, которые читает человек, тут не пишутся.

Движок — бесплатные модели OpenRouter (src/services/or_free.py, копия скилла
openrouter-free): список тянется живьём из /api/v1/models и фильтруется по
нулевой цене, упавшая модель уходит в cooldown, запрос идёт к следующей.
Транспорт — curl: WAF OpenRouter режет requests по TLS-отпечатку.
"""
from __future__ import annotations

from .or_free import chat_json as _chat_json


def chat_json(system: str, user: str, max_tokens: int = 4000) -> dict | list:
    return _chat_json(system, user, max_tokens=max_tokens)
