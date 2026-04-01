"""
eval_score.py — Phase 2: Score cached answers with RAGAS
Reads eval_cache.json — no pipeline calls at all.
Metrics: Context Precision + Context Recall (Faithfulness needs 70b model)
"""
import asyncio, json, math, os, sys, time, warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["LANGCHAIN_TRACING_V2"] = "false"
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

CACHE_FILE    = Path("eval_cache.json")
FLAG_THRESHOLD = 0.50
METRIC_NAMES  = ["context_precision", "context_recall"]
DELAY_BETWEEN = 8

if not CACHE_FILE.exists():
    print("eval_cache.json not found — run eval_generate.py first"); sys.exit(1)

all_records = json.loads(CACHE_FILE.read_text(encoding="utf-8"))["records"]
good = [r for r in all_records if not r.get("error") and r.get("answer")]
print(f"Loaded {len(good)}/{len(all_records)} valid records from eval_cache.json\n")
if not good:
    print("No valid records."); sys.exit(1)

print("Checking imports...")
try:
    from langchain_groq import ChatGroq
    from ragas import evaluate, EvaluationDataset
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import ContextPrecision, ContextRecall
    from ragas.llms import LangchainLLMWrapper
    print("Imports OK\n")
except ImportError as e:
    print(f"Import error: {e}"); sys.exit(1)

GROQ_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_KEY:
    print("GROQ_API_KEY not in .env"); sys.exit(1)

def make_llm():
    return LangchainLLMWrapper(
        ChatGroq(model="llama-3.1-8b-instant", temperature=0.0,
                 max_tokens=2048, api_key=GROQ_KEY, request_timeout=90)
    )

METRIC_CLASSES = {
    "context_precision": lambda: ContextPrecision(llm=make_llm()),
    "context_recall": lambda: ContextRecall(llm=make_llm()),
}

est = len(good) * len(METRIC_NAMES) * (DELAY_BETWEEN + 25) // 60 + 1
print("Judge: llama-3.1-8b-instant")
print(f"Scoring {len(good)} questions x {len(METRIC_NAMES)} metrics sequentially")
print(f"Estimated time: ~{est} minutes\n")

results = {r["question"]: {} for r in good}

for metric_name, metric_factory in METRIC_CLASSES.items():
    print(f"\n-------- Metric: {metric_name} ----------------------")
    for i, rec in enumerate(good):
        q = rec["question"]
        print(f"  [{i+1:02d}/{len(good)}] {q[:60]}...", end=" ", flush=True)
        sample  = SingleTurnSample(
            user_input=q, response=rec["answer"],
            retrieved_contexts=rec["contexts"], reference=rec["ground_truth"]
        )
        dataset = EvaluationDataset(samples=[sample])
        score   = float("nan")
        for attempt in range(1, 4):
            try:
                row = evaluate(dataset=dataset, metrics=[metric_factory()],
                                 raise_exceptions=False).to_pandas().iloc[0]
                val = row.get(metric_name)
                score = round(float(val), 4) if (
                    val is not None and not (isinstance(val, float) and math.isnan(val))
                ) else float("nan")
                asyncio.set_event_loop(asyncio.new_event_loop())
                break
            except RuntimeError:
                pass
            except KeyboardInterrupt:
                print("\nInterrupted - saving partial results...")
                _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                Path("eval_partial.json").write_text(
                    json.dumps({"run_at": _ts, "partial": True,
                                "results": results}, indent=2), encoding="utf-8")
                print("Partial results saved to eval_partial.json")
                sys.exit(0)
            except Exception as e:
                wait = DELAY_BETWEEN * attempt * 2
                print(f"\n     Attempt {attempt} failed ({e.__class__.__name__}) — waiting {wait}s...")
                time.sleep(wait)

        results[q][metric_name] = score
        print(f"{score:.3f}" if not math.isnan(score) else "n/a")
        if i < len(good) - 1:
            time.sleep(DELAY_BETWEEN)

print("\nScoring complete\n")

ts, full_results, flagged = datetime.now().strftime("%Y%m%d_%H%M%S"), [], []
for i, rec in enumerate(good):
    scores  = results[rec["question"]]
    valid_v = [v for v in scores.values() if not math.isnan(v)]
    avg     = round(sum(valid_v) / len(valid_v), 4) if valid_v else float("nan")
    entry   = {
        "id": i+1, "question": rec["question"],
        "answer": rec["answer"][:300] + ("..." if len(rec["answer"]) > 300 else ""),
        "latency_ms": rec.get("latency_ms", 0),
        "confidence": rec.get("confidence", ""),
        "scores": {m: scores.get(m, float("nan")) for m in METRIC_NAMES},
        "avg_score": avg,
    }
    full_results.append(entry)
    low = {m: v for m, v in entry["scores"].items()
           if not math.isnan(v) and v < FLAG_THRESHOLD}
    if low: flagged.append({**entry, "low_metrics": low})

Path("ragas_results.json").write_text(
    json.dumps({"run_at": ts, "results": full_results}, indent=2, ensure_ascii=False), encoding="utf-8")
Path("ragas_flagged.json").write_text(
    json.dumps({"run_at": ts, "flagged": flagged}, indent=2, ensure_ascii=False), encoding="utf-8")

W      = 52
header = f"{'#':<4} {'Question':<{W}} {'Prec':>6} {'Rcll':>6} {'Avg':>6}"
sep    = "─" * len(header)
lines  = [
    "="*len(header),
    "  NaijaCodex — RAGAS Evaluation Results",
    f"  {ts}  |  {len(full_results)} questions  |  {len(flagged)} flagged",
    "  Metrics: Context Precision + Context Recall",
    "  (Faithfulness excluded — requires 70b model)",
    "="*len(header), header, sep,
]

def fs(v): return f"{v:>6.3f}" if not math.isnan(v) else "   n/a"

for r in full_results:
    s    = r["scores"]
    flag = "! " if any(not math.isnan(v) and v < FLAG_THRESHOLD for v in s.values()) else "  "
    lines.append(f"{r['id']:<2}{flag}{r['question'][:W]:<{W}} "
                 f"{fs(s['context_precision'])} {fs(s['context_recall'])} {fs(r['avg_score'])}")

lines.append(sep)
for_avg = {m: [r["scores"][m] for r in full_results
               if not math.isnan(r["scores"].get(m, float("nan")))]
           for m in METRIC_NAMES}
avgs = {m: round(sum(v)/len(v), 4) if v else float("nan") for m, v in for_avg.items()}
ov   = [v for v in avgs.values() if not math.isnan(v)]
oa   = round(sum(ov)/len(ov), 4) if ov else float("nan")
lines.append(f"{'AVG':<4}{'':.<{W}} "
             f"{fs(avgs['context_precision'])} {fs(avgs['context_recall'])} {fs(oa)}")
lines.append("="*len(header))

if flagged:
    lines.append(f"\n{len(flagged)} question(s) flagged (score < {FLAG_THRESHOLD}):")
    for f in flagged:
        lines.append(f"  [{f['id']:02d}] {f['question'][:70]}")
        for m, v in f["low_metrics"].items():
            lines.append(f"       {m:<26}: {v:.3f}")
    lines.append("")

lines += ["ragas_results.json", "ragas_flagged.json", "ragas_summary.txt"]
summary = "\n".join(lines)
Path("ragas_summary.txt").write_text(summary, encoding="utf-8")
print(summary)
print("\nDone. Paste ragas_summary.txt here to review.")
