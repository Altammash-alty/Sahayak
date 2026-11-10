"""
Audio Quality Gate and DSP Preprocessing (app/audio.py)
Uses numpy and scipy only. Pure signal processing, no heavy external C-libraries.
"""

import io
import wave
import numpy as np
from scipy import signal
from typing import Tuple, Dict, Any, Optional
from app.config import config

class AudioQualityReport:
    def __init__(
        self,
        decision: str,              # "PASS", "CLEANED", "REJECT"
        reject_reason: Optional[str] = None, # "TOO_SHORT", "TOO_QUIET", "TOO_NOISY", "CLIPPED", "NO_SPEECH"
        duration_sec: float = 0.0,
        rms_dbfs: float = -100.0,
        peak_dbfs: float = -100.0,
        clipping_ratio: float = 0.0,
        speech_ratio: float = 0.0,
        snr_db: float = 0.0,
        processed_wav_bytes: Optional[bytes] = None
    ):
        self.decision = decision
        self.reject_reason = reject_reason
        self.duration_sec = duration_sec
        self.rms_dbfs = rms_dbfs
        self.peak_dbfs = peak_dbfs
        self.clipping_ratio = clipping_ratio
        self.speech_ratio = speech_ratio
        self.snr_db = snr_db
        self.processed_wav_bytes = processed_wav_bytes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reject_reason": self.reject_reason,
            "duration_sec": round(self.duration_sec, 3),
            "rms_dbfs": round(self.rms_dbfs, 2),
            "peak_dbfs": round(self.peak_dbfs, 2),
            "clipping_ratio": round(self.clipping_ratio, 4),
            "speech_ratio": round(self.speech_ratio, 3),
            "snr_db": round(self.snr_db, 2)
        }

def read_wav_to_np(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
    """Reads raw WAV bytes into float32 array in range [-1.0, 1.0] and sample rate."""
    with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw_frames = wf.readframes(n_frames)

    if sampwidth == 2:
        samples = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 1:
        samples = (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif sampwidth == 4:
        samples = np.frombuffer(raw_frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    if n_channels > 1:
        # Convert to mono by averaging channels
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    return samples, sr

def write_np_to_wav(samples: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Encodes float32 numpy array into 16-bit PCM WAV bytes."""
    clipped = np.clip(samples, -1.0, 1.0)
    int16_samples = (clipped * 32767.0).astype(np.int16)
    
    out_buf = io.BytesIO()
    with wave.open(out_buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())
        
    return out_buf.getvalue()

def compute_metrics(samples: np.ndarray, sr: int) -> Dict[str, float]:
    """Computes duration, RMS (dBFS), peak (dBFS), clipping ratio, VAD speech ratio, and rough SNR."""
    n_samples = len(samples)
    if n_samples == 0:
        return {
            "duration": 0.0, "rms_dbfs": -100.0, "peak_dbfs": -100.0,
            "clipping_ratio": 0.0, "speech_ratio": 0.0, "snr_db": 0.0
        }

    duration = n_samples / float(sr)
    peak = np.max(np.abs(samples)) if n_samples > 0 else 0.0
    peak_dbfs = 20.0 * np.log10(peak) if peak > 1e-6 else -100.0

    rms = np.sqrt(np.mean(samples ** 2))
    rms_dbfs = 20.0 * np.log10(rms) if rms > 1e-6 else -100.0

    # Clipping detection: sample near +/- 0.999
    clipping_count = np.sum(np.abs(samples) >= 0.99)
    clipping_ratio = float(clipping_count) / float(n_samples)

    # Frame-based Energy VAD (frame length 30ms, hop 15ms)
    frame_len = int(sr * 0.03)
    hop_len = int(sr * 0.015)
    if n_samples >= frame_len:
        num_frames = 1 + (n_samples - frame_len) // hop_len
        frame_energies = []
        for i in range(num_frames):
            frame = samples[i * hop_len : i * hop_len + frame_len]
            frame_energies.append(np.mean(frame ** 2))
        frame_energies = np.array(frame_energies)
        
        # Noise floor estimate (lowest 15th percentile)
        noise_floor = np.percentile(frame_energies, 15)
        # Threshold for speech energy (3x noise floor and min -50 dBFS)
        vad_thresh = max(noise_floor * 3.0, 1e-5)
        speech_frames = np.sum(frame_energies > vad_thresh)
        speech_ratio = float(speech_frames) / float(len(frame_energies))

        # Rough SNR (Signal to Noise Ratio)
        speech_energy = np.mean(frame_energies[frame_energies > vad_thresh]) if speech_frames > 0 else noise_floor
        snr_ratio = (speech_energy + 1e-9) / (noise_floor + 1e-9)
        snr_db = float(10.0 * np.log10(snr_ratio))
    else:
        speech_ratio = 1.0 if rms_dbfs > -45.0 else 0.0
        snr_db = 15.0 if rms_dbfs > -45.0 else 0.0

    return {
        "duration": duration,
        "rms_dbfs": rms_dbfs,
        "peak_dbfs": peak_dbfs,
        "clipping_ratio": clipping_ratio,
        "speech_ratio": speech_ratio,
        "snr_db": snr_db
    }

def apply_light_cleanup(samples: np.ndarray, sr: int) -> np.ndarray:
    """
    Applies light DSP cleanup:
    1. 80 Hz high-pass Butterworth filter (removes mic rumble, DC offset, wind pop).
    2. Trims leading and trailing silence.
    3. Peak-normalizes to -1.0 dBFS (0.891).
    """
    if len(samples) < int(sr * 0.1):
        return samples

    # 1. 80 Hz 2nd order highpass filter
    sos = signal.butter(2, 80.0, 'hp', fs=sr, output='sos')
    filtered = signal.sosfilt(sos, samples)

    # 2. Trim silence (energy < -48 dBFS frame)
    frame_len = int(sr * 0.02)
    hop_len = int(sr * 0.01)
    if len(filtered) >= frame_len:
        energies = []
        for i in range(0, len(filtered) - frame_len, hop_len):
            energies.append(np.mean(filtered[i : i + frame_len] ** 2))
        energies = np.array(energies)
        silence_thresh = 10.0 ** (-4.8) # ~ -48 dBFS
        active_indices = np.where(energies > silence_thresh)[0]
        if len(active_indices) > 0:
            start_sample = max(0, active_indices[0] * hop_len - int(sr * 0.05)) # keep 50ms padding
            end_sample = min(len(filtered), (active_indices[-1] + 1) * hop_len + int(sr * 0.05))
            trimmed = filtered[start_sample:end_sample]
        else:
            trimmed = filtered
    else:
        trimmed = filtered

    # 3. Peak-normalize to -1.0 dBFS (factor = 0.891)
    peak = np.max(np.abs(trimmed)) if len(trimmed) > 0 else 0.0
    if peak > 1e-4:
        target_peak = 0.89125 # -1 dBFS
        normalized = trimmed * (target_peak / peak)
    else:
        normalized = trimmed

    return normalized

def evaluate_audio_quality(raw_wav_bytes: bytes) -> AudioQualityReport:
    """
    Evaluates audio against the quality gate thresholds.
    Returns AudioQualityReport with PASS, CLEANED, or REJECT and processed WAV bytes.
    """
    if not config.ENABLE_AUDIO_QUALITY_GATE:
        return AudioQualityReport(decision="PASS", processed_wav_bytes=raw_wav_bytes)

    try:
        samples, sr = read_wav_to_np(raw_wav_bytes)
    except Exception as e:
        return AudioQualityReport(
            decision="REJECT",
            reject_reason="INVALID_FORMAT",
            processed_wav_bytes=raw_wav_bytes
        )

    # Initial raw metrics
    metrics = compute_metrics(samples, sr)
    
    # 1. Reject checks on raw audio
    if metrics["duration"] < config.MIN_DURATION_SEC:
        return AudioQualityReport(
            decision="REJECT",
            reject_reason="TOO_SHORT",
            duration_sec=metrics["duration"],
            rms_dbfs=metrics["rms_dbfs"],
            peak_dbfs=metrics["peak_dbfs"],
            clipping_ratio=metrics["clipping_ratio"],
            speech_ratio=metrics["speech_ratio"],
            snr_db=metrics["snr_db"],
            processed_wav_bytes=raw_wav_bytes
        )

    if metrics["clipping_ratio"] > config.MAX_CLIPPING_RATIO:
        return AudioQualityReport(
            decision="REJECT",
            reject_reason="CLIPPED",
            duration_sec=metrics["duration"],
            rms_dbfs=metrics["rms_dbfs"],
            peak_dbfs=metrics["peak_dbfs"],
            clipping_ratio=metrics["clipping_ratio"],
            speech_ratio=metrics["speech_ratio"],
            snr_db=metrics["snr_db"],
            processed_wav_bytes=raw_wav_bytes
        )

    # Apply cleanup if enabled
    cleaned_samples = apply_light_cleanup(samples, sr) if config.ENABLE_AUDIO_CLEANUP else samples
    cleaned_metrics = compute_metrics(cleaned_samples, sr)

    # 2. ADVISORY GATE (Phase 4 / F1):
    # Only hard-reject extreme digital silence (<-60 dBFS) or corrupted signal
    # Otherwise pass cleaned audio to Prisma STT so user's intent is never prematurely blocked
    if cleaned_metrics["rms_dbfs"] < -60.0:
        return AudioQualityReport(
            decision="REJECT",
            reject_reason="TOO_QUIET",
            duration_sec=cleaned_metrics["duration"],
            rms_dbfs=cleaned_metrics["rms_dbfs"],
            peak_dbfs=cleaned_metrics["peak_dbfs"],
            clipping_ratio=cleaned_metrics["clipping_ratio"],
            speech_ratio=cleaned_metrics["speech_ratio"],
            snr_db=cleaned_metrics["snr_db"],
            processed_wav_bytes=raw_wav_bytes
        )

    # Decision: CLEANED or PASS (advisory metrics logged, but audio forwarded to Prisma)
    out_bytes = write_np_to_wav(cleaned_samples, sr)
    decision = "CLEANED" if config.ENABLE_AUDIO_CLEANUP else "PASS"

    return AudioQualityReport(
        decision=decision,
        reject_reason=None,
        duration_sec=cleaned_metrics["duration"],
        rms_dbfs=cleaned_metrics["rms_dbfs"],
        peak_dbfs=cleaned_metrics["peak_dbfs"],
        clipping_ratio=cleaned_metrics["clipping_ratio"],
        speech_ratio=cleaned_metrics["speech_ratio"],
        snr_db=cleaned_metrics["snr_db"],
        processed_wav_bytes=out_bytes
    )
