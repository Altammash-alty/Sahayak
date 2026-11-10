"""
Runtime Configuration and Feature Flags for Sahayak
All Phase 2 behaviors sit behind flags so they can be switched off cleanly.
"""

from pydantic import BaseModel
import os

class AppConfig(BaseModel):
    # T1: Audio Quality Gate Flags & Thresholds
    ENABLE_AUDIO_QUALITY_GATE: bool = True
    ENABLE_AUDIO_CLEANUP: bool = True               # 80Hz high-pass, trim silence, peak-normalize
    ENABLE_SPECTRAL_DENOISE: bool = False            # Spectral noise reduction OFF by default
    
    MIN_DURATION_SEC: float = 0.4                   # Minimum audio duration
    MIN_SPEECH_RATIO: float = 0.15                  # Energy VAD speech-to-total ratio threshold (15%)
    MIN_RMS_DBFS: float = -45.0                     # Minimum RMS level (dBFS)
    MAX_CLIPPING_RATIO: float = 0.02                # Max 2% clipping allowed
    MIN_SNR_DB: float = 8.0                         # Minimum Signal-to-Noise Ratio (dB)
    MAX_CONSECUTIVE_REJECTS: int = 2                # Max rejects before referral to helpline

    # T2: Call Mode Flags
    ENABLE_CALL_MODE: bool = True
    CALL_SILENCE_TIMEOUT_SEC: float = 8.0           # Prompt caller after 8s silence
    MAX_CALL_DURATION_SEC: float = 300.0            # 5 minute call limit

    # T3: Latency & Caching Flags
    ENABLE_TTS_DISK_CACHE: bool = True
    ENABLE_PERSISTENT_HTTP_CLIENT: bool = True
    ENABLE_STREAMING_TTS: bool = False              # Evaluated in T3

    # T4: UI Flags
    ENABLE_DEMO_MODE: bool = True
    ENABLE_TEXT_SIZE_TOGGLE: bool = True

config = AppConfig()

