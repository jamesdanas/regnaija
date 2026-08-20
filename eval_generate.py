"""
eval_generate.py — Phase 1: Run pipeline, cache answers to eval_cache.json
Run this once when Groq quota is fresh. Takes ~60s, uses ~20k tokens.
Re-running is safe — it overwrites the cache.
"""
import json, re, sys, time
from pathlib import Path

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
     "ground_truth": "Participants must comply with the CBN Risk-based Cybersecurity Framework, implement information security and privacy procedures, ensure API security, obtain customer consent before sharing data, and comply with the Nigerian Data Protection Regulation."},
    {"question": "What penalties apply for violating NITDA IT regulations?",
     "ground_truth": "NITDA can investigate, sanction, and penalise organisations that violate IT regulations. Under the NDPR, organisations face fines up to 2% of annual gross revenue or 10 million naira for data protection non-compliance."},
    {"question": "What are the licensing requirements for payment service providers under CBN?",
     "ground_truth": "Payment service providers must obtain a CBN licence by meeting minimum capital thresholds, having fit and proper directors, demonstrating technical capability, and complying with AML/CFT regulations and CBN cybersecurity frameworks."},
    {"question": "How does the Nigeria Data Protection Act 2023 define personal data?",
     "ground_truth": "The NDPA 2023 defines personal data as any information relating to an identified or identifiable natural person, including names, identification numbers, location data, online identifiers, and factors specific to physical, physiological, genetic, mental, economic, cultural, or social identity."},
    {"question": "What SEC disclosure requirements apply to public companies in Nigeria?",
     "ground_truth": "Public companies must make continuous and periodic disclosures to the SEC including annual reports, quarterly reports, material information disclosures, and insider trading reports."},
    {"question": "What incident response obligations do banks have under CBN cybersecurity guidelines?",
     "ground_truth": "Banks must establish an incident management framework covering detection, containment, eradication, recovery, and post-incident review. They must report material cyber incidents to the CBN within prescribed timeframes and maintain incident logs for regulatory examination."},
]

print("Loading pipeline...")
from src.graph.rag_graph import RegNaijaPipeline
pipeline = RegNaijaPipeline()
print("Pipeline ready\n")

print(f"Running {len(GOLDEN_SET)} questions (2s gap to avoid rate limits)...\n")
records = []
for i, item in enumerate(GOLDEN_SET, 1):
    q, gt = item["question"], item["ground_truth"]
    print(f"[{i:02d}/{len(GOLDEN_SET)}] {q[:70]}")
    t0 = time.time()
    try:
        result = pipeline.query(q)
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
                        "ground_truth": gt, "latency_ms": latency,
                        "confidence": conf, "agencies": result.get("agencies_searched", []),
                        "error": False})
    except Exception as e:
        print(f"Error: {e}")
        records.append({"question": q, "answer": "", "contexts": [],
                        "ground_truth": gt, "error": True, "error_msg": str(e)})

    if i < len(GOLDEN_SET):
        time.sleep(2)

good  = [r for r in records if not r["error"]]
fails = [r for r in records if r["error"]]
print(f"\n{len(good)}/10 succeeded, {len(fails)}/10 failed")

Path("eval_cache.json").write_text(
    json.dumps({"records": records}, indent=2, ensure_ascii=False), encoding="utf-8")
print("Saved to eval_cache.json")

if fails:
    print("\nFailed questions:")
    for r in fails:
        print(f"{r['question'][:70]}")
        print(f"Reason: {r.get('error_msg','')[:120]}")
    print("\nFix: wait for Groq quota reset (midnight UTC) then re-run.")
else:
    print("\nAll done! Now run: python eval_score.py")
