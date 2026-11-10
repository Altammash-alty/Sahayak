import json
import csv
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dialogue import DialogueManager
from app.db import init_db

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
RESULTS_CSV = Path(__file__).resolve().parent / "results.csv"
RESULTS_MD = Path(__file__).resolve().parent / "results.md"

def run_evaluation():
    init_db()
    
    scenario_files = list(SCENARIOS_DIR.glob("*.json"))
    all_results = []
    
    print(f"Discovered {len(scenario_files)} scenario file(s). Running evaluation...")

    for sf in scenario_files:
        with open(sf, "r", encoding="utf-8") as f:
            scenarios = json.load(f)

        for sc in scenarios:
            sc_id = sc["id"]
            lang = sc["language"]
            expected = sc["expected_verdict"]
            scheme_id = None
            state = "START"
            slots = {}
            turns_taken = 0
            start_time = time.time()
            final_eval = None
            completed = False

            for user_input in sc["turns"]:
                turns_taken += 1
                agent_text, state, scheme_id, slots, is_done, eval_res = DialogueManager.process_turn(
                    user_transcript=user_input,
                    current_language=lang,
                    detected_language=lang,
                    scheme_id=scheme_id,
                    current_state=state,
                    collected_slots=slots
                )
                if is_done:
                    completed = True
                    final_eval = eval_res
                    break

            latency = time.time() - start_time
            actual_verdict = final_eval["verdict"] if final_eval else "UNSURE"
            is_accurate = (actual_verdict == expected)

            all_results.append({
                "scenario_id": sc_id,
                "language": lang,
                "scheme": sc["scheme"],
                "expected": expected,
                "actual": actual_verdict,
                "accurate": is_accurate,
                "completed": completed,
                "turns": turns_taken,
                "latency_sec": round(latency, 4)
            })

    # Write CSV
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["scenario_id", "language", "scheme", "expected", "actual", "accurate", "completed", "turns", "latency_sec"])
        writer.writeheader()
        writer.writerows(all_results)

    # Compute Aggregate Metrics per language
    metrics_by_lang = {}
    for r in all_results:
        l = r["language"]
        if l not in metrics_by_lang:
            metrics_by_lang[l] = {"total": 0, "completed": 0, "accurate": 0, "turns": 0, "latencies": []}
        m = metrics_by_lang[l]
        m["total"] += 1
        if r["completed"]:
            m["completed"] += 1
        if r["accurate"]:
            m["accurate"] += 1
        m["turns"] += r["turns"]
        m["latencies"].append(r["latency_sec"])

    # Generate Markdown Table
    md_lines = [
        "# Evaluation Benchmark Results",
        "",
        f"**Evaluated at:** {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Total Scenarios:** {len(all_results)} across 3 languages (`hi-IN`, `en-IN`, `ta-IN`)",
        "",
        "## Summary Metrics by Language",
        "",
        "| Language | Total Scenarios | Task Completion Rate | Eligibility Accuracy | Avg Turns / Call | Avg Execution Latency |",
        "|---|---|---|---|---|---|"
    ]

    for lang, m in metrics_by_lang.items():
        comp_rate = (m["completed"] / m["total"]) * 100
        acc_rate = (m["accurate"] / m["total"]) * 100
        avg_turns = m["turns"] / m["total"]
        avg_lat = sum(m["latencies"]) / len(m["latencies"])
        md_lines.append(f"| `{lang}` | {m['total']} | {comp_rate:.1f}% | **{acc_rate:.1f}%** | {avg_turns:.1f} | {avg_lat*1000:.1f} ms |")

    md_lines.extend([
        "",
        "## Detailed Results",
        "",
        "| ID | Language | Scheme | Expected | Actual | Match | Completed | Turns |",
        "|---|---|---|---|---|---|---|---|"
    ])

    for r in all_results:
        status_icon = "✅" if r["accurate"] else "❌"
        md_lines.append(f"| `{r['scenario_id']}` | {r['language']} | `{r['scheme']}` | `{r['expected']}` | `{r['actual']}` | {status_icon} | {r['completed']} | {r['turns']} |")

    with open(RESULTS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"Evaluation complete. Results written to {RESULTS_CSV} and {RESULTS_MD}")

if __name__ == "__main__":
    run_evaluation()

