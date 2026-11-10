import os
import time
import logging
from typing import Optional, Dict, Any
import httpx
from dotenv import load_dotenv

load_dotenv()

GNANI_API_KEY = os.getenv("GNANI_API_KEY")

STT_URL = "https://api.vachana.ai/stt/v3"
TTS_URL = "https://api.vachana.ai/api/v1/tts/inference"

logger = logging.getLogger("gnani_client")

# Preferred Timbre v2.5 voices mapped by language code
VOICE_MAP = {
    "hi-IN": "Nalini",
    "en-IN": "Kaveri",
    "ta-IN": "Asmita",
    "te-IN": "Suhana",
    "kn-IN": "Saanvi",
    "mr-IN": "Ishaan",
    "bn-IN": "Dhruva",
    "gu-IN": "Falak",
    "pa-IN": "Mehuli",
    "ml-IN": "Reshma"
}

# Persistent HTTP Client with Connection Pooling & Keep-Alive (T3)
_persistent_client = httpx.Client(
    timeout=httpx.Timeout(30.0, connect=10.0),
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0)
)

class GnaniAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}

def _get_headers() -> Dict[str, str]:
    api_key = os.getenv("GNANI_API_KEY") or GNANI_API_KEY
    if not api_key or api_key == "your_gnani_api_key_here":
        raise GnaniAPIError("GNANI_API_KEY is missing or invalid in environment.")
    return {
        "X-API-Key-ID": api_key
    }

def transcribe_audio(
    audio_bytes: bytes,
    language_code: str = "hi-IN",
    model: str = "prisma-v3.0",
    max_retries: int = 1,
    timeout_sec: float = 30.0
) -> Dict[str, Any]:
    """
    Transcribes audio bytes (WAV, 16kHz mono) using Gnani Prisma with persistent HTTP keep-alive.
    Returns dict containing transcript, latency, detected_language_code, etc.
    """
    headers = _get_headers()
    files = {
        "audio_file": ("audio.wav", audio_bytes, "audio/wav")
    }
    data = {
        "language_code": language_code,
        "model": model,
        "format": "transcribe"
    }

    last_exc = None
    for attempt in range(max_retries + 1):
        start_time = time.time()
        try:
            response = _persistent_client.post(STT_URL, headers=headers, files=files, data=data)
            latency = time.time() - start_time
            if response.status_code == 200:
                res_json = response.json()
                res_json["measured_latency"] = latency
                return res_json
            elif response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = 2 ** attempt if response.status_code == 429 else 0.5 * (attempt + 1)
                logger.warning("STT HTTP %s on attempt %d, retrying in %.1fs",
                               response.status_code, attempt + 1, wait)
                time.sleep(wait)
                continue
            else:
                try:
                    err_data = response.json()
                except Exception:
                    err_data = {"raw_text": response.text}
                raise GnaniAPIError(
                    f"Gnani STT failed with HTTP {response.status_code}: {err_data}",
                    status_code=response.status_code,
                    details=err_data
                )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise GnaniAPIError(f"Gnani STT network/timeout error: {str(e)}") from e
        except Exception as e:
            if isinstance(e, GnaniAPIError):
                raise
            raise GnaniAPIError(f"Unexpected error in STT call: {str(e)}") from e

    raise GnaniAPIError(f"Gnani STT failed after retries: {str(last_exc)}")

def synthesize_speech(
    text: str,
    language_code: str = "hi-IN",
    voice: Optional[str] = None,
    model: str = "timbre-v2.5",
    sample_rate: int = 16000,
    speed: float = 1.0,
    max_retries: int = 4,
    timeout_sec: float = 30.0
) -> Dict[str, Any]:
    """
    Synthesizes speech using Gnani Timbre REST endpoint with persistent HTTP connection.
    Returns dict with 'audio_bytes', 'measured_latency', 'sample_rate'.

    Retry policy (Gnani RATE_LIMITED = "only 1 active request at a time"):
      - 429 -> exponential backoff: 1s, 2s, 4s, 8s before each retry
      - 5xx -> shorter backoff: 0.5s, 1s, 2s, 4s
    """
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    
    selected_voice = voice or VOICE_MAP.get(language_code, "Nalini")

    payload = {
        "text": text,
        "voice": selected_voice,
        "model": model,
        "language": language_code,
        "speed": speed,
        "audio_config": {
            "sample_rate": sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav"
        }
    }

    last_exc = None
    for attempt in range(max_retries + 1):
        start_time = time.time()
        try:
            response = _persistent_client.post(TTS_URL, headers=headers, json=payload)
            latency = time.time() - start_time
            if response.status_code == 200:
                return {
                    "audio_bytes": response.content,
                    "measured_latency": latency,
                    "sample_rate": sample_rate,
                    "voice": selected_voice
                }
            elif response.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                # 429 = "Only 1 active request at a time" – use longer exponential backoff
                if response.status_code == 429:
                    wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                else:
                    wait = 0.5 * (attempt + 1)
                logger.warning("TTS HTTP %s on attempt %d/%d, retrying in %.1fs",
                               response.status_code, attempt + 1, max_retries + 1, wait)
                time.sleep(wait)
                continue
            else:
                try:
                    err_data = response.json()
                except Exception:
                    err_data = {"raw_text": response.text}
                raise GnaniAPIError(
                    f"Gnani TTS failed with HTTP {response.status_code}: {err_data}",
                    status_code=response.status_code,
                    details=err_data
                )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise GnaniAPIError(f"Gnani TTS network/timeout error: {str(e)}") from e
        except Exception as e:
            if isinstance(e, GnaniAPIError):
                raise
            raise GnaniAPIError(f"Unexpected error in TTS call: {str(e)}") from e

    raise GnaniAPIError(f"Gnani TTS failed after retries: {str(last_exc)}")
