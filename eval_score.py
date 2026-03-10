"""
eval_score.py — Phase 2: Score cached answers with RAGAS
Reads eval_cache.json — does NOT call the pipeline at all.
Judge: llama-3.1-8b-instant (500k TPD) — safe to run multiple times.
"""
import json, os, sys, time, warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["LANGCHAIN_TRACING_V2"] = "false"
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

CACHE_FILE = Path("eval_cache.json")
FLAG_THRESHOLD = 0.50
METRIC_NAMES = ["faithfulness", "context_precision", "context_recall"]
DELAY_SECS = 12   # 12s between questions — 8b-instant is faster but still has RPM limits

#  Load cache 
if not CACHE_FILE.exists():
    print("eval_cache.json not found — run eval_generate.py first")
    sys.exit(1)

all_records = json.loads(CACHE_FILE.read_text(encoding="utf-8"))["records"]
good = [r for r in all_records if not r.get("error") and r.get("answer")]
print(f"Loaded {len(good)}/{len(all_records)} valid records from eval_cache.json\n")
if not good:
    print("No valid records — re-run eval_generate.py"); sys.exit(1)

# Imports 
print("Checking imports...")
try:
    from langchain_groq import ChatGroq
    from ragas import evaluate, EvaluationDataset
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import Faithfulness, ContextPrecision, ContextRecall
    from ragas.llms import LangchainLLMWrapper
    print("Imports OK\n")
except ImportError as e:
    print(f"{e}"); sys.exit(1)

# Judge (8b-instant — 500k TPD) 
import os as _os
GROQ_KEY = _os.getenv("GROQ_API_KEY", "")
if not GROQ_KEY:
    print("GROQ_API_KEY not in .env"); sys.exit(1)

print("Judge: llama-3.1-8b-instant (500k TPD — safe for full eval)...")
ragas_llm = LangchainLLMWrapper(
    ChatGroq(model="llama-3.1-8b-instant", temperature=0.0,
             max_tokens=1024, api_key=GROQ_KEY)
)
metrics = [
    Faithfulness(llm=ragas_llm),
    ContextPrecision(llm=ragas_llm),
    ContextRecall(llm=ragas_llm),
]
print(f"Judge ready — scoring {len(good)} questions ({DELAY_SECS}s gap between each)\n")
print(f"Estimated time: ~{len(good) * (DELAY_SECS + 20) // 60 + 1} minutes\n")

# Score one-by-one 
all_scores = []
for i, rec in enumerate(good):
    print(f"[{i+1:02d}/{len(good)}] {rec['question'][:65]}...")
    sample  = SingleTurnSample(user_input=rec["question"], response=rec["answer"],
                                retrieved_contexts=rec["contexts"],
                                reference=rec["ground_truth"])
    dataset = EvaluationDataset(samples=[sample])
    for attempt in range(1, 4):
        try:
            row = evaluate(dataset=dataset, metrics=metrics,
                              raise_exceptions=False).to_pandas().iloc[0]
            scores = {m: round(float(row.get(m) or 0), 4) for m in METRIC_NAMES}
            print(f"          faith={scores['faithfulness']:.3f}  "
                  f"prec={scores['context_precision']:.3f}  "
                  f"rcll={scores['context_recall']:.3f}")
            all_scores.append(scores)
            break
        except Exception as e:
            wait = DELAY_SECS * attempt * 2
            print(f"Attempt {attempt} failed — waiting {wait}s... ({e})")
            time.sleep(wait)
    else:
        print(f"All attempts failed — recording zeros")
        all_scores.append({m: 0.0 for m in METRIC_NAMES})

    if i < len(good) - 1:
        print(f"{DELAY_SECS}s pause...")
        time.sleep(DELAY_SECS)

print("\nScoring complete\n")

# Merge + save 
ts, full_results, flagged = datetime.now().strftime("%Y%m%d_%H%M%S"), [], []
for i, (rec, scores) in enumerate(zip(good, all_scores)):
    avg   = round(sum(scores.values()) / len(scores), 4)
    entry = {"id": i+1, "question": rec["question"],
              "answer": rec["answer"][:300] + ("..." if len(rec["answer"]) > 300 else ""),
              "latency_ms": rec.get("latency_ms", 0),
              "confidence": rec.get("confidence", ""),
              "scores": scores, "avg_score": avg}
    full_results.append(entry)
    low = {m: v for m, v in scores.items() if v < FLAG_THRESHOLD}
    if low: flagged.append({**entry, "low_metrics": low})

Path("ragas_results.json").write_text(
    json.dumps({"run_at": ts, "results": full_results}, indent=2, ensure_ascii=False), encoding="utf-8")
Path("ragas_flagged.json").write_text(
    json.dumps({"run_at": ts, "flagged": flagged}, indent=2, ensure_ascii=False), encoding="utf-8")

# Summary table 
W = 52
header = f"{'#':<4} {'Question':<{W}} {'Faith':>6} {'Prec':>6} {'Rcll':>6} {'Avg':>6}"
sep = "─" * len(header)
lines = ["═"*len(header), "  NaijaCodex — RAGAS Evaluation Results",
          f"{ts}  |  {len(full_results)} questions  |  {len(flagged)} flagged",
          f"Judge: llama-3.1-8b-instant  |  Metrics: Faithfulness · Precision · Recall",
          "═"*len(header), header, sep]

for r in full_results:
    s = r["scores"]
    flag = "⚠ " if any(v < FLAG_THRESHOLD for v in s.values()) else "  "
    lines.append(f"{r['id']:<2}{flag}{r['question'][:W]:<{W}} "
                 f"{s['faithfulness']:>6.3f} {s['context_precision']:>6.3f} "
                 f"{s['context_recall']:>6.3f} {r['avg_score']:>6.3f}")

lines.append(sep)
avgs = {m: round(sum(r["scores"][m] for r in full_results)/len(full_results), 4)
               for m in METRIC_NAMES}
overall_avg = round(sum(avgs.values())/len(avgs), 4)
lines.append(f"{'AVG':<4}{'':.<{W}} {avgs['faithfulness']:>6.3f} "
             f"{avgs['context_precision']:>6.3f} {avgs['context_recall']:>6.3f} {overall_avg:>6.3f}")
lines.append("═"*len(header))

if flagged:
    lines.append(f"\n{len(flagged)} question(s) flagged (score < {FLAG_THRESHOLD}):")
    for f in flagged:
        lines.append(f"[{f['id']:02d}] {f['question'][:70]}")
        for m, v in f["low_metrics"].items():
            lines.append(f"{m:<26}: {v:.3f}")
    lines.append("")

lines += ["ragas_results.json", "ragas_flagged.json", "ragas_summary.txt"]
summary = "\n".join(lines)
Path("ragas_summary.txt").write_text(summary, encoding="utf-8")
print(summary)
print("\nDone. Paste ragas_summary.txt here to review.")
