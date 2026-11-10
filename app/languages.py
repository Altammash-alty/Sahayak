"""
app/languages.py – Data-driven language registry for Sahayak.

Provides the canonical list of supported languages with STT codes,
Timbre voice assignments, script metadata, and enabled flags.

Used by:
- app/main.py startup validator (validate_all_languages)
- app/gnani.py VOICE_MAP (single source of truth)
- app/i18n/ loader (is_language_supported)
- Phase 4 C6: new languages added here, behind enabled=False flags until
  i18n files and TTS voices are verified.
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("app.languages")

# ---------------------------------------------------------------------------
# Language Registry
# ---------------------------------------------------------------------------
LANGUAGES = [
    {
        "code": "hi-IN",
        "name": "Hindi",
        "native": "हिन्दी",
        "stt_code": "hi-IN",
        "voice": "Nalini",
        "script": "devanagari",
        "enabled": True,
        "verified": True,
    },
    {
        "code": "en-IN",
        "name": "English",
        "native": "English",
        "stt_code": "en-IN",
        "voice": "Kaveri",
        "script": "latin",
        "enabled": True,
        "verified": True,
    },
    {
        "code": "ta-IN",
        "name": "Tamil",
        "native": "தமிழ்",
        "stt_code": "ta-IN",
        "voice": "Asmita",
        "script": "tamil",
        "enabled": True,
        "verified": True,
    },
    # --- Phase 4 C6: New languages (enabled=False until i18n + TTS smoke-tested) ---
    {
        "code": "bn-IN",
        "name": "Bengali",
        "native": "বাংলা",
        "stt_code": "bn-IN",
        "voice": "Dhruva",
        "script": "bengali",
        "enabled": False,
        "verified": False,
    },
    {
        "code": "mr-IN",
        "name": "Marathi",
        "native": "मराठी",
        "stt_code": "mr-IN",
        "voice": "Ishaan",
        "script": "devanagari",
        "enabled": False,
        "verified": False,
    },
    {
        "code": "te-IN",
        "name": "Telugu",
        "native": "తెలుగు",
        "stt_code": "te-IN",
        "voice": "Suhana",
        "script": "telugu",
        "enabled": False,
        "verified": False,
    },
    {
        "code": "gu-IN",
        "name": "Gujarati",
        "native": "ગુજરાતી",
        "stt_code": "gu-IN",
        "voice": "Falak",
        "script": "gujarati",
        "enabled": False,
        "verified": False,
    },
    {
        "code": "kn-IN",
        "name": "Kannada",
        "native": "ಕನ್ನಡ",
        "stt_code": "kn-IN",
        "voice": "Saanvi",
        "script": "kannada",
        "enabled": False,
        "verified": False,
    },
]

# Convenience maps
_BY_CODE = {lang["code"]: lang for lang in LANGUAGES}

ENABLED_LANGUAGES: List[dict] = [lang for lang in LANGUAGES if lang["enabled"]]
ENABLED_CODES: List[str] = [lang["code"] for lang in ENABLED_LANGUAGES]

# Voice map (single source of truth – imported by app/gnani.py where needed)
VOICE_MAP: dict = {lang["code"]: lang["voice"] for lang in LANGUAGES}


def is_language_supported(code: str) -> bool:
    """Returns True if the language code is enabled."""
    lang = _BY_CODE.get(code)
    return lang is not None and lang["enabled"]


def get_language(code: str) -> Optional[dict]:
    """Returns language metadata dict or None."""
    return _BY_CODE.get(code)


def validate_all_languages() -> None:
    """
    Startup validator: for every enabled language, check that the
    corresponding i18n JSON file exists and contains the required keys.
    Logs a LOUD warning (not exception) if keys are missing, so the server
    still starts and degraded-mode fallback is possible.
    """
    i18n_dir = Path(__file__).resolve().parent / "i18n"
    required_keys = [
        "greeting",
        "handoff",
        "reasks",
    ]
    for lang in ENABLED_LANGUAGES:
        code = lang["code"]
        lang_code_short = code.split("-")[0]  # e.g. "hi" from "hi-IN"
        i18n_path = i18n_dir / f"{lang_code_short}.json"
        if not i18n_path.exists():
            logger.error(
                "STARTUP VALIDATOR: i18n file missing for enabled language '%s': %s",
                code, i18n_path
            )
            continue
        import json
        try:
            with open(i18n_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            logger.error("STARTUP VALIDATOR: Failed to parse i18n file %s: %s", i18n_path, exc)
            continue
        missing = [k for k in required_keys if k not in data]
        if missing:
            logger.error(
                "STARTUP VALIDATOR: i18n file for '%s' is missing required keys: %s",
                code, missing
            )
        else:
            logger.info("STARTUP VALIDATOR: Language '%s' (%s) OK", code, lang["native"])
