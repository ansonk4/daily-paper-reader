from __future__ import annotations

import os
from typing import Any, Mapping


DEFAULT_ANALYSIS_LANGUAGE = "en"
SUPPORTED_ANALYSIS_LANGUAGES = {"zh-Hans", "zh-Hant", "en"}

_LANGUAGE_ALIASES = {
    "zh": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh_cn": "zh-Hans",
    "zh-hans": "zh-Hans",
    "zh_hans": "zh-Hans",
    "zh-hans-cn": "zh-Hans",
    "cn": "zh-Hans",
    "chinese": "zh-Hans",
    "simplified": "zh-Hans",
    "simplified-chinese": "zh-Hans",
    "chinese-simplified": "zh-Hans",
    "zh-tw": "zh-Hant",
    "zh_tw": "zh-Hant",
    "zh-hk": "zh-Hant",
    "zh_hk": "zh-Hant",
    "zh-hant": "zh-Hant",
    "zh_hant": "zh-Hant",
    "traditional": "zh-Hant",
    "traditional-chinese": "zh-Hant",
    "chinese-traditional": "zh-Hant",
    "hant": "zh-Hant",
    "en": "en",
    "en-us": "en",
    "en_us": "en",
    "english": "en",
    "eng": "en",
}


def normalize_analysis_language(value: Any, default: str = DEFAULT_ANALYSIS_LANGUAGE) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    if text in SUPPORTED_ANALYSIS_LANGUAGES:
        return text
    key = text.lower().replace(" ", "-")
    return _LANGUAGE_ALIASES.get(key, default)


def resolve_analysis_language(
    config: Mapping[str, Any] | None = None,
    default: str = DEFAULT_ANALYSIS_LANGUAGE,
) -> str:
    env_value = os.getenv("DPR_ANALYSIS_LANGUAGE") or os.getenv("ANALYSIS_LANGUAGE")
    if env_value:
        return normalize_analysis_language(env_value, default=default)

    setting = {}
    if isinstance(config, Mapping):
        raw_setting = config.get("arxiv_paper_setting") or {}
        if isinstance(raw_setting, Mapping):
            setting = raw_setting

    for key in ("analysis_language", "output_language", "language"):
        value = setting.get(key)
        if value:
            return normalize_analysis_language(value, default=default)
    return default


def is_english_analysis_language(language: Any) -> bool:
    return normalize_analysis_language(language) == "en"


def is_traditional_chinese_analysis_language(language: Any) -> bool:
    return normalize_analysis_language(language) == "zh-Hant"


def analysis_language_display_name(language: Any) -> str:
    normalized = normalize_analysis_language(language)
    if normalized == "en":
        return "English"
    if normalized == "zh-Hant":
        return "Traditional Chinese"
    return "Simplified Chinese"
