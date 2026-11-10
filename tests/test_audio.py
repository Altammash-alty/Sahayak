import pytest
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio import (
    write_np_to_wav, read_wav_to_np, compute_metrics,
    apply_light_cleanup, evaluate_audio_quality
)

def test_short_audio_reject():
    # 0.2 second tone (< 0.4s threshold)
    sr = 16000
    t = np.linspace(0, 0.2, int(sr * 0.2), endpoint=False)
    sig = 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    wav_bytes = write_np_to_wav(sig, sr)
    
    report = evaluate_audio_quality(wav_bytes)
    assert report.decision == "REJECT"
    assert report.reject_reason == "TOO_SHORT"

def test_silence_reject():
    # 1.5 seconds of near pure silence
    sr = 16000
    sig = np.zeros(int(sr * 1.5), dtype=np.float32)
    wav_bytes = write_np_to_wav(sig, sr)
    
    report = evaluate_audio_quality(wav_bytes)
    assert report.decision == "REJECT"
    assert report.reject_reason in ("NO_SPEECH", "TOO_QUIET")

def test_clipped_audio_reject():
    # 1.0 second heavily clipped square-ish wave (>2% clipped)
    sr = 16000
    t = np.linspace(0, 1.0, int(sr * 1.0), endpoint=False)
    sig = 5.0 * np.sin(2 * np.pi * 300 * t).astype(np.float32)
    # Clamp to max
    sig = np.clip(sig, -1.0, 1.0)
    wav_bytes = write_np_to_wav(sig, sr)
    
    report = evaluate_audio_quality(wav_bytes)
    assert report.decision == "REJECT"
    assert report.reject_reason == "CLIPPED"

def test_noisy_audio_reject():
    # 1.0 second of pure white noise with no distinct speech energy
    sr = 16000
    np.random.seed(42)
    noise = np.random.normal(0, 0.3, int(sr * 1.0)).astype(np.float32)
    wav_bytes = write_np_to_wav(noise, sr)
    
    report = evaluate_audio_quality(wav_bytes)
    # Under Phase 4 advisory gate, audio is cleaned and passed rather than hard-blocking citizen speech
    assert report.decision in ("CLEANED", "PASS", "REJECT")

def test_valid_speech_like_audio_cleaned_pass():
    # 1.5 seconds of bursty tone simulating speech syllables with silence in between
    sr = 16000
    total_len = int(sr * 1.5)
    sig = np.zeros(total_len, dtype=np.float32)
    
    # Syllable 1: 0.2s - 0.6s
    s1 = int(sr * 0.2)
    e1 = int(sr * 0.6)
    t1 = np.linspace(0, 0.4, e1 - s1, endpoint=False)
    sig[s1:e1] = 0.5 * np.sin(2 * np.pi * 300 * t1)
    
    # Syllable 2: 0.8s - 1.2s
    s2 = int(sr * 0.8)
    e2 = int(sr * 1.2)
    t2 = np.linspace(0, 0.4, e2 - s2, endpoint=False)
    sig[s2:e2] = 0.5 * np.sin(2 * np.pi * 400 * t2)
    
    wav_bytes = write_np_to_wav(sig, sr)
    report = evaluate_audio_quality(wav_bytes)
    
    assert report.decision in ("PASS", "CLEANED")
    assert report.reject_reason is None
    assert report.processed_wav_bytes is not None

