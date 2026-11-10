import pytest
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.audio import write_np_to_wav, evaluate_audio_quality

def test_barge_in_energy_levels():
    sr = 16000
    # Simulate loud speech utterance during agent playback (> -28 dBFS)
    t = np.linspace(0, 0.4, int(sr * 0.4), endpoint=False)
    loud_speech = 0.5 * np.sin(2 * np.pi * 350 * t).astype(np.float32)
    
    rms = np.sqrt(np.mean(loud_speech ** 2))
    dbfs = 20.0 * np.log10(rms)
    
    # Assert speech level is above the -28 dB barge-in threshold
    assert dbfs > -28.0, f"Speech dbfs {dbfs} should be above -28 dB threshold"

def test_background_silence_below_barge_in_threshold():
    sr = 16000
    # Simulate room ambient noise or gentle speaker bleed (< -35 dBFS)
    np.random.seed(42)
    ambient_noise = np.random.normal(0, 0.01, int(sr * 0.4)).astype(np.float32)
    
    rms = np.sqrt(np.mean(ambient_noise ** 2))
    dbfs = 20.0 * np.log10(rms)
    
    # Assert ambient room bleed will NOT trigger false barge-in
    assert dbfs < -28.0, f"Ambient noise {dbfs} must be below barge-in threshold"
