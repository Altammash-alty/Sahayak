"""
Pre-warms and pre-caches fixed TTS prompts for all supported languages and voices.
Run once during build/startup or via CLI to guarantee sub-second latency for all static prompts.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache import get_cached_tts
from app.dialogue import get_i18n
from app.config import config

LANGUAGES = ["hi-IN", "en-IN", "ta-IN"]

def prewarm_tts_prompts():
    print("Pre-warming fixed TTS prompts to disk cache...")
    total_cached = 0

    for lang in LANGUAGES:
        i18n = get_i18n(lang)
        prompts = [
            i18n["greeting"],
            i18n["unclear"],
            i18n["handoff"],
            i18n["scheme_not_recognized"],
            i18n["invalid_value"]
        ]
        
        # Add all question prompts
        for q_text in i18n["questions"].values():
            prompts.append(q_text)

        # Add all re-ask prompt variants
        for variant_list in i18n.get("reasks", {}).values():
            for v_text in variant_list:
                prompts.append(v_text)

        print(f"Pre-caching {len(prompts)} prompts for {lang}...")
        for p in prompts:
            try:
                get_cached_tts(p, lang)
                total_cached += 1
            except Exception as e:
                print(f"Warning: Failed to cache prompt '{p[:30]}...': {e}")

    print(f"Pre-warming complete! Total prompts ready in disk cache: {total_cached}")

if __name__ == "__main__":
    prewarm_tts_prompts()

