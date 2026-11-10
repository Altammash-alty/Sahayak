import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gnani import synthesize_speech, transcribe_audio

def test_hindi_roundtrip():
    print("Testing Hindi TTS (Nalini, hi-IN)...")
    text_in = "नमस्ते, पीएम किसान योजना में आपका स्वागत है।"
    tts_res = synthesize_speech(text_in, language_code="hi-IN", voice="Nalini")
    audio = tts_res["audio_bytes"]
    print(f"TTS Success! Latency: {tts_res['measured_latency']:.2f}s, Audio bytes: {len(audio)}")
    
    print("Testing Hindi STT (Prisma v3.0, hi-IN)...")
    stt_res = transcribe_audio(audio, language_code="hi-IN")
    transcript = stt_res.get("transcript", "")
    print(f"STT Success! Latency: {stt_res.get('measured_latency', 0):.2f}s, Transcript: {transcript}")
    assert len(transcript.strip()) > 0, "Hindi transcript was empty"

def test_english_roundtrip():
    print("\nTesting English TTS (Kaveri, en-IN)...")
    text_in = "Welcome to the government scheme eligibility assistant."
    tts_res = synthesize_speech(text_in, language_code="en-IN", voice="Kaveri")
    audio = tts_res["audio_bytes"]
    print(f"TTS Success! Latency: {tts_res['measured_latency']:.2f}s, Audio bytes: {len(audio)}")
    
    print("Testing English STT (Prisma v3.0, en-IN)...")
    stt_res = transcribe_audio(audio, language_code="en-IN")
    transcript = stt_res.get("transcript", "")
    print(f"STT Success! Latency: {stt_res.get('measured_latency', 0):.2f}s, Transcript: {transcript}")
    assert len(transcript.strip()) > 0, "English transcript was empty"

if __name__ == "__main__":
    try:
        test_hindi_roundtrip()
        test_english_roundtrip()
        print("\nAll Gnani smoke tests passed successfully!")
    except Exception as e:
        print(f"\nSmoke test FAILED: {e}", file=sys.stderr)
        sys.exit(1)
