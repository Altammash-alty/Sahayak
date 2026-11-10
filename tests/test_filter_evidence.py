import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from app.audio import write_np_to_wav, evaluate_audio_quality, read_wav_to_np
from app.config import config
from app.gnani import synthesize_speech, transcribe_audio

def run_filter_comparison():
    print("Generating speech sample via Gnani Timbre...")
    tts = synthesize_speech("हाँ मेरे पास खेती की ज़मीन है", language_code="hi-IN", voice="Nalini")
    clean_bytes = tts["audio_bytes"]

    # 1. Clean speech
    config.ENABLE_AUDIO_CLEANUP = True
    rep_on = evaluate_audio_quality(clean_bytes)
    stt_on = transcribe_audio(rep_on.processed_wav_bytes, language_code="hi-IN")

    config.ENABLE_AUDIO_CLEANUP = False
    rep_off = evaluate_audio_quality(clean_bytes)
    stt_off = transcribe_audio(rep_off.processed_wav_bytes, language_code="hi-IN")

    # 2. Add 60Hz rumble / microphone handling noise
    samples, sr = read_wav_to_np(clean_bytes)
    t = np.linspace(0, len(samples)/sr, len(samples), endpoint=False)
    rumble = 0.25 * np.sin(2 * np.pi * 60 * t).astype(np.float32)
    noisy_samples = samples + rumble
    noisy_bytes = write_np_to_wav(noisy_samples, sr)

    config.ENABLE_AUDIO_CLEANUP = True
    rep_noisy_on = evaluate_audio_quality(noisy_bytes)
    stt_noisy_on = transcribe_audio(rep_noisy_on.processed_wav_bytes, language_code="hi-IN")

    config.ENABLE_AUDIO_CLEANUP = False
    rep_noisy_off = evaluate_audio_quality(noisy_bytes)
    stt_noisy_off = transcribe_audio(rep_noisy_off.processed_wav_bytes, language_code="hi-IN")

    print(f"CLEAN: Filter ON -> '{stt_on.get('transcript')}' | Filter OFF -> '{stt_off.get('transcript')}'")
    print(f"RUMBLE NOISE: Filter ON -> '{stt_noisy_on.get('transcript')}' | Filter OFF -> '{stt_noisy_off.get('transcript')}'")

    config.ENABLE_AUDIO_CLEANUP = True

if __name__ == "__main__":
    run_filter_comparison()
