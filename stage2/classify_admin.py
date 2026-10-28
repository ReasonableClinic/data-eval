#!/usr/bin/env python3
"""Mark administrative criteria in criteria.jsonl (field "administrative": true/false).

Administrative = a procedural requirement fulfilled at enrollment by the patient or the site, not a medical
fact about the patient: informed consent, willingness / ability to comply with visits, agreeing to use
contraception, agreeing not to join another trial, providing samples or tissue for research, registering,
being able to travel to the site. These criteria stay UNKNOWN for a record, so at trial level they do not
block "eligible" (common format v0.5). The flag is a property of the criterion, so it is set once per
criterion (patient-independent) instead of per patient x trial pair.

Usage:
  python3 classify_admin.py --criteria ../ctgov_v1/criteria.jsonl --candidates ../ctgov_v1/trial_candidates.jsonl \
      --provider openrouter --model openai/gpt-oss-120b
  (writes the flag into the same file after making criteria.jsonl.bak; only trials named in --candidates
   are classified unless --all; criteria already flagged are skipped)
"""
import argparse, json, os, shutil, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_lib as G  # noqa: E402

PROMPT = """Below are clinical-trial eligibility criteria, one per line: criterion_id | type | text.

Return the ids of the ADMINISTRATIVE criteria: procedural requirements fulfilled at enrollment by the participant
or the study site, not medical facts about the patient. Examples: signed informed consent; willing / able to comply
with study visits and procedures; agrees to use contraception or not to donate sperm/eggs; agrees not to take part in
another interventional study; provides archival tissue, a fresh biopsy or blood samples for research; can travel to
the site; registration or insurance formalities.

NOT administrative (these are medical): diagnosis, disease stage, biomarkers, lab values, performance status, life
expectancy, prior or current treatments, pregnancy or breastfeeding status, comorbidities, current participation in
another trial as a fact about the patient's recent treatment ("received an investigational drug within 28 days").
If a line mixes an administrative and a medical requirement, it is NOT administrative.

Criteria:
{criteria}

Return only JSON: {{"administrative": ["<criterion_id>", ...]}}"""


def classify(a, batch):
    text = "\n".join(f"{c['criterion_id']} | {c['type']} | {c['original_text'][:400]}" for c in batch)
    want = {c["criterion_id"] for c in batch}
    for attempt in range(3):
        try:
            out, usage = G.call_llm(a.provider, a.model, PROMPT.format(criteria=text), 0.0, max_tokens=8000)
            ids = G.parse_json(out).get("administrative", [])
            if isinstance(ids, list):
                return {i for i in ids if i in want}, usage
        except Exception as e:
            if type(e).__name__ in G.FATAL_ERRORS:
                raise
            print(f"  retry batch {batch[0]['criterion_id']}: {type(e).__name__}: {str(e)[:100]}")
    return None, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--criteria", required=True)
    ap.add_argument("--candidates", help="trial_candidates.jsonl: classify only trials named there")
    ap.add_argument("--all", action="store_true", help="classify every trial in the file")
    ap.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    G.preflight(a.provider)

    rows = G.load_jsonl(a.criteria)
    keep = None
    if a.candidates and not a.all:
        keep = {t for r in G.load_jsonl(a.candidates) for t in r.get("trial_ids", [])}
    todo = [c for c in rows if "administrative" not in c and (keep is None or c["trial_id"] in keep)]
    batches = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"{len(todo)} criteria to classify in {len(batches)} batches")
    flags, tin, tout, cost, failed = {}, 0, 0, 0.0, 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(classify, a, b): b for b in batches}
        for n, fut in enumerate(as_completed(futs), 1):
            b = futs[fut]
            ids, usage = fut.result()
            if ids is None:
                failed += 1
                continue
            for c in b:
                flags[c["criterion_id"]] = c["criterion_id"] in ids
            tin += usage.get("input_tokens", 0); tout += usage.get("output_tokens", 0); cost += usage.get("cost") or 0
            if n % 10 == 0 or n == len(batches):
                print(f"  {n}/{len(batches)} batches")
    if not os.path.exists(a.criteria + ".bak"):
        shutil.copy(a.criteria, a.criteria + ".bak")
    for c in rows:
        if c["criterion_id"] in flags:
            c["administrative"] = flags[c["criterion_id"]]
    G.write_jsonl(a.criteria, rows)
    n_admin = sum(flags.values())
    print(f"done: {len(flags)} classified, {n_admin} administrative ({100 * n_admin / max(1, len(flags)):.0f}%), "
          f"{failed} batches failed (run again to retry them); tokens {tin} in / {tout} out"
          + (f", charged ${cost:.3f}" if cost else ""))
    examples = [c for c in rows if flags.get(c["criterion_id"])][:12]
    for c in examples:
        print("  admin:", c["criterion_id"], c["original_text"][:90])

if __name__ == "__main__":
    main()
