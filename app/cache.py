import hashlib
import os
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any
from app.gnani import synthesize_speech, VOICE_MAP, GnaniAPIError
from app.dialogue import validate_script_match

logger = logging.getLogger("app.cache")

CACHE_DIR = Path(__file__).resolve().parent.parent / "audio_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

class ScriptMismatchError(ValueError):
    pass

def get_cached_tts(text: str, language_code: str, voice: Optional[str] = None) -> bytes:
    """
    Retrieves synthesized audio from disk cache if present;
    otherwise calls Gnani Timbre TTS, caches it, and returns the audio bytes.
    Strictly enforces:
    1. Cache key = (voice, language, text_hash).
    2. Script safety check: blocks Devanagari text leaking into English/Tamil TTS requests (Task B2).

    On GnaniAPIError (including 429 after all retries), raises to caller so they can
    return a localised error response instead of crashing with HTTP 500.
    """
    selected_voice = voice or VOICE_MAP.get(language_code, "Nalini")

    # Safety check: Text must match target language script
    if not validate_script_match(text, language_code):
        err_msg = f"Language leakage detected! Attempted to synthesize '{text[:40]}...' under language '{language_code}'."
        logger.error(err_msg)
        raise ScriptMismatchError(err_msg)

    # Key = voice + language + text_hash
    text_hash = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    key_str = f"{selected_voice}_{language_code}_{text_hash}"
    file_name = f"{hashlib.sha256(key_str.encode('utf-8')).hexdigest()}.wav"
    cache_path = CACHE_DIR / file_name
    
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            return f.read()
            
    # Call Gnani Timbre TTS with explicit voice and language
    # GnaniAPIError propagates to caller; synthesize_speech already retries internally.
    res = synthesize_speech(text=text, language_code=language_code, voice=selected_voice)
    audio_bytes = res["audio_bytes"]
    
    with open(cache_path, "wb") as f:
        f.write(audio_bytes)
        
    return audio_bytes
