"""
evaluate_ragas.py — NaijaCodex RAGAS Evaluation 
Compatible: ragas==0.2.6 | langchain==0.3.0 | langchain-community==0.3.0
Judge: Groq llama-3.3-70b

Fixes applied vs first run:
  1. ResponseRelevancy dropped — returns 0.000 with non-OpenAI embeddings in ragas 0.2.6
  2. Sequential evaluation with 8s delay between questions — avoids Groq rate limit
  3. raise_exceptions=False so one failure doesn't wipe all scores
"""
import json, os, re, sys, time, warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ["LANGCHAIN_TRACING_V2"] = "false"
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

GOLDEN_SET = [
    {"question": "What cybersecurity frameworks must fintechs comply with under CBN guidelines?",
     "ground_truth": "Fintechs must comply with the CBN Risk-based Cybersecurity Framework and Guidelines for Deposit Money Banks and Payment Service Providers, and the CBN Risk-based Cybersecurity Framework for Other Financial Institutions. They must develop security policies, adopt risk management practices, and establish incident management procedures."},
    {"question": "What are the data subject rights under the Nigeria Data Protection Act 2023?",
     "ground_truth": "Under the NDPA 2023, data subjects have the right to be informed, right of access, right to rectification, right to erasure, right to restrict processing, right to data portability, right to object, and rights related to automated decision-making and profiling."},
    {"question": "What are the capital requirements for stockbrokers under SEC rules?",
     "ground_truth": "SEC requires stockbrokers and broker-dealers to maintain minimum paid-up capital as specified in the SEC Rules and Regulations. Capital adequacy requirements are set for different categories of market operators in the Nigerian capital market."},
    {"question": "What are the obligations of data controllers under NDPC 2023?",
     "ground_truth": "Data controllers must obtain lawful consent, implement technical and organisational security measures, appoint a Data Protection Officer where required, conduct Data Protection Impact Assessments for high-risk processing, register with the NDPC, and report data breaches within 72 hours."},
    {"question": "What open banking participation requirements apply under CBN policy?",
     "ground_truth": "Participants must comply with the CBN Risk-based Cybersecurity Framework, implement information security and privacy procedures, ensure API security, obtain customer consent before sharing data, and comply with the Nigerian Data Protection Regulation as stated in Section 9.2 of the CBN Open Banking Policy."},
    {"question": "What penalties apply for violating NITDA IT regulations?",
     "ground_truth": "NITDA can investigate, sanction, and penalise organisations that violate IT regulations under Section 6.0 of NITDA compliance and enforcement powers. Under the NDPR, organisations face fines up to 2% of annual gross revenue or 10 million naira for data protection non-compliance."},
    {"question": "What are the licensing requirements for payment service providers under CBN?",
     "ground_truth": "Payment service providers must obtain a CBN licence by meeting minimum capital thresholds, having fit and proper directors, demonstrating technical capability, and complying with AML/CFT regulations and CBN cybersecurity frameworks."},
    {"question": "How does the Nigeria Data Protection Act 2023 define personal data?",
     "ground_truth": "The NDPA 2023 defines personal data as any information relating to an identified or identifiable natural person, including names, identification numbers, location data, online identifiers, and factors specific to physical, physiological, genetic, mental, economic, cultural, or social identity."},
    {"question": "What SEC disclosure requirements apply to public companies in Nigeria?",
     "ground_truth": "Public companies must make continuous and periodic disclosures to the SEC including annual reports, quarterly reports, material information disclosures, and insider trading reports. The SEC Rules mandate timely disclosure of any information that could materially affect investment decisions."},
    {"question": "What incident response obligations do banks have under CBN cybersecurity guidelines?",
     "ground_truth": "Banks must establish an incident management framework covering detection, containment, eradication, recovery, and post-incident review. They must report material cyber incidents to the CBN within prescribed timeframes and maintain incident logs for regulatory examination."},
]

FLAG_THRESHOLD = 0.50
METRIC_NAMES = ["faithfulness", "context_precision", "context_recall"]
DELAY_SECS = 8   # pause between per-question evaluations to avoid Groq rate limit

# Imports 
print("Checking imports...")
try:
    import os
    from langchain_groq import ChatGroq
    from ragas import evaluate, EvaluationDataset
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import Faithfulness, ContextPrecision, ContextRecall
    from ragas.llms import LangchainLLMWrapper
    print("All imports OK\n")
except ImportError as e:
    print(f"Import error: {e}"); sys.exit(1)

# Judge 
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_KEY:
    print("GROQ_API_KEY not set in .env"); sys.exit(1)

print("Configuring Groq (llama-3.3-70b) as judge...")
ragas_llm = LangchainLLMWrapper(
    ChatGroq(model="llama-3.1-8b-instant", temperature=0.0,
             max_tokens=1024, api_key=GROQ_KEY)
)
metrics = [
    Faithfulness(llm=ragas_llm),
    ContextPrecision(llm=ragas_llm),
    ContextRecall(llm=ragas_llm),
]
print("Judge ready (ResponseRelevancy excluded — ragas 0.2.6 non-OpenAI limitation)\n")

# Pipeline 
print("Loading NaijaCodex pipeline...")
from src.graph.rag_graph import NaijaCodexPipeline
pipeline = NaijaCodexPipeline()
print("Pipeline ready\n")

# Run golden questions 
print(f"Running {len(GOLDEN_SET)} golden questions...\n")
records = []
for i, item in enumerate(GOLDEN_SET, 1):
    q, gt = item["question"], item["ground_truth"]
    print(f"[{i:02d}/{len(GOLDEN_SET)}] {q[:70]}")
    t0 = time.time()
    try:
        result = pipeline.query(q)
    except Exception as e:
        print(f"Pipeline error: {e}")
        records.append({"question": q, "answer": f"ERROR: {e}",
                        "contexts": [], "ground_truth": gt, "error": True})
        continue
    latency = int((time.time() - t0) * 1000)
    answer = re.sub(r"\[SOURCE:[^\]]+\]", "", result.get("answer", "")).strip()
    docs = result.get("retrieved_docs", [])
    if docs:
        contexts = []
        for d in docs:
            if hasattr(d, "page_content"):  
                contexts.append(d.page_content)
            elif isinstance(d, dict):        
                contexts.append(d.get("page_content", str(d)))
            else:                            
                contexts.append(str(d))
    else:
        raw = result.get("citations", "")
        contexts = [raw] if raw else ["No context retrieved."]
    conf = str(result.get("confidence", "?"))
    print(f"{len(contexts)} chunks · {latency}ms · conf={conf[:4]}")
    records.append({"question": q, "answer": answer, "contexts": contexts,
                    "ground_truth": gt, "error": False, "latency_ms": latency,
                    "confidence": conf, "agencies": result.get("agencies_searched", [])})

good = [r for r in records if not r["error"]]
print(f"\n{len(good)}/{len(records)} pipeline queries succeeded\n")
if not good:
    print("No successful queries."); sys.exit(1)

# Evaluate ONE question at a time with delay 
print(f"Evaluating {len(good)} samples one-by-one ({DELAY_SECS}s delay between each)...\n")
print(f"Estimated time: ~{len(good) * (DELAY_SECS + 15) // 60 + 1} minutes\n")

all_scores = []
for i, rec in enumerate(good):
    print(f"Scoring [{i+1:02d}/{len(good)}] {rec['question'][:60]}...")
    sample = SingleTurnSample(user_input=rec["question"], response=rec["answer"],
                                retrieved_contexts=rec["contexts"], reference=rec["ground_truth"])
    dataset = EvaluationDataset(samples=[sample])
    attempt = 0
    while attempt < 3:
        try:
            row = evaluate(dataset=dataset, metrics=metrics,
                           raise_exceptions=False).to_pandas().iloc[0]
            scores = {m: round(float(row.get(m) or 0), 4) for m in METRIC_NAMES}
            print(f"faith={scores['faithfulness']:.3f}  "
                  f"prec={scores['context_precision']:.3f}  "
                  f"rcll={scores['context_recall']:.3f}")
            all_scores.append(scores)
            break
        except Exception as e:
            attempt += 1
            wait = DELAY_SECS * attempt * 2
            print(f"Attempt {attempt} failed: {e} — waiting {wait}s...")
            time.sleep(wait)
    else:
        print("All 3 attempts failed - recording zeros")
        all_scores.append({m: 0.0 for m in METRIC_NAMES})

    if i < len(good) - 1:
        print(f"Waiting {DELAY_SECS}s before next question...")
        time.sleep(DELAY_SECS)

print("\nScoring complete\n")

#  Merge + flag 
ts, full_results, flagged = datetime.now().strftime("%Y%m%d_%H%M%S"), [], []
for i, (rec, scores) in enumerate(zip(good, all_scores)):
    avg   = round(sum(scores.values()) / len(scores), 4)
    entry = {"id": i+1, "question": rec["question"],
              "answer": rec["answer"][:300] + ("..." if len(rec["answer"]) > 300 else ""),
              "ground_truth": rec["ground_truth"], "latency_ms": rec["latency_ms"],
              "confidence": rec.get("confidence",""), "agencies": rec.get("agencies",[]),
              "scores": scores, "avg_score": avg}
    full_results.append(entry)
    low = {m: v for m, v in scores.items() if v < FLAG_THRESHOLD}
    if low: 
        flagged.append({**entry, "low_metrics": low})

# Save 
Path("ragas_results.json").write_text(
    json.dumps({"run_at": ts, "results": full_results}, indent=2, ensure_ascii=False), encoding="utf-8")
Path("ragas_flagged.json").write_text(
    json.dumps({"run_at": ts, "flagged": flagged}, indent=2, ensure_ascii=False), encoding="utf-8")

#  Summary table 
W = 52
header = f"{'#':<4} {'Question':<{W}} {'Faith':>6} {'Prec':>6} {'Rcll':>6} {'Avg':>6}"
sep = "─" * len(header)
lines = ["═"*len(header), "NaijaCodex — RAGAS Evaluation Results",
          f"{ts}  |  {len(full_results)} questions  |  {len(flagged)} flagged",
          "Metrics: Faithfulness · Context Precision · Context Recall",
          "(ResponseRelevancy excluded — ragas 0.2.6 + non-OpenAI embeddings returns 0.000)",
          "═"*len(header), header, sep]

for r in full_results:
    s = r["scores"]
    flag = "⚠ " if any(v < FLAG_THRESHOLD for v in s.values()) else "  "
    lines.append(f"{r['id']:<2}{flag}{r['question'][:W]:<{W}} "
                 f"{s['faithfulness']:>6.3f} {s['context_precision']:>6.3f} "
                 f"{s['context_recall']:>6.3f} {r['avg_score']:>6.3f}")

lines.append(sep)
avgs = {m: round(sum(r["scores"][m] for r in full_results)/len(full_results), 4) for m in METRIC_NAMES}
overall_avg = round(sum(avgs.values())/len(avgs), 4)
lines.append(f"{'AVG':<4}{'':.<{W}} {avgs['faithfulness']:>6.3f} "
             f"{avgs['context_precision']:>6.3f} {avgs['context_recall']:>6.3f} {overall_avg:>6.3f}")
lines.append("═"*len(header))

if flagged:
    lines.append(f"\n{len(flagged)} flagged (score < {FLAG_THRESHOLD}):")
    for f in flagged:
        lines.append(f"[{f['id']:02d}] {f['question'][:70]}")
        for m, v in f["low_metrics"].items():
            lines.append(f"{m:<26}: {v:.3f}")
    lines.append("")

lines += ["ragas_results.json", "ragas_flagged.json", "ragas_summary.txt"]
summary = "\n".join(lines)
Path("ragas_summary.txt").write_text(summary, encoding="utf-8")
print(summary)
print("\nDone. Paste ragas_summary.txt here to review scores.")