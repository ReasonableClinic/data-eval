#!/usr/bin/env python3
"""Step 3: independent LLM check of each variant's target criterion (same prompt and rules as the gold labeler).

For every variant the model sees the variant record and ONLY the target criterion, blind to the expected answer.
The base patient is judged the same way as a control (it should come out PASS).
Rows where the model disagrees with the expected judgment go to review.

Usage (stage2/variants, OPENROUTER_API_KEY set):
  python3 verify_variants.py --split dev --dir out_dev --provider openrouter --model openai/gpt-oss-120b
Output: <dir>/verify_report.csv (agree = status and reason match; status_agree = status only)
"""
import argparse, csv, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
_argv, sys.argv = sys.argv, [sys.argv[0]]
import gold_lib as G  # noqa: E402
import label_gold as L  # noqa: E402
sys.argv = _argv
ROOT = os.path.join(HERE, "..", "..")
SETS = {"dev": "patients_v2.jsonl", "test": "patients_eval_v2.jsonl"}
EXPECT = {"violation": ("FAIL", "VIOLATED"), "missing": ("UNKNOWN", "MISSING"), "expired": ("UNKNOWN", "EXPIRED"),
          "conflict": ("CONFLICT", "CONFLICT"), "unsupported": ("UNKNOWN", "UNSUPPORTED")}
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731


def judge(a, p, t, c):
    prompt = L.PROMPT.format(as_of=p["as_of"], patient=L.patient_text(p), trial=L.trial_text(t), criteria=L.criteria_text([c]))
    for _ in range(3):
        try:
            text, _u = G.call_llm(a.provider, a.model, prompt, 0.0, max_tokens=8000)
            rows = G.parse_json(text).get("criteria") or []
            r = next(x for x in rows if x.get("criterion_id") == c["criterion_id"])
            ev = " | ".join(f"{e.get('doc_id')}: {e.get('quote')}" for e in r.get("evidence") or [] if isinstance(e, dict))
            return r.get("expected_status"), r.get("reason"), r.get("expected_action"), ev, r.get("rationale", "")
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ in G.FATAL_ERRORS:
                raise
    return "ERROR", "", "", "", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=SETS, required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-base", action="store_true", help="skip the base-patient control")
    a = ap.parse_args()
    G.preflight(a.provider)
    P = {p["patient_id"]: p for p in jl(os.path.join(ROOT, SETS[a.split]))}
    V = {p["patient_id"]: p for p in jl(os.path.join(a.dir, "patients_variants.jsonl"))}
    M = json.load(open(os.path.join(a.dir, "id_map_variants.json")))
    T = {t["trial_id"]: t for t in jl(os.path.join(ROOT, "ctgov_v1/trials.jsonl"))}
    C = {c["criterion_id"]: c for c in jl(os.path.join(ROOT, "ctgov_v1/criteria.jsonl"))}
    notes = {}
    for g in jl(os.path.join(a.dir, "gold_variants.jsonl")):
        if (g.get("injection") or {}).get("doc_id"):
            notes[g["patient_id"]] = (g["trial_id"], g["injection"])
    jobs = []
    for pid, m in M.items():
        tid, inj = notes[pid]
        c = C[m["target_criterion"]]
        jobs.append(("variant", pid, m, V[pid], T[tid], c, inj))
        if not a.no_base:
            jobs.append(("base", pid, m, P[m["base_patient_id"]], T[tid], c, inj))
    res = {}
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(judge, a, j[3], j[4], j[5]): j for j in jobs}
        for n, f in enumerate(as_completed(futs), 1):
            j = futs[f]
            res[(j[0], j[1])] = f.result()
            if n % 10 == 0 or n == len(jobs):
                print(f"  {n}/{len(jobs)}")
    out = os.path.join(a.dir, "verify_report.csv")
    agree = st_agree = 0
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["patient_id", "base_patient_id", "variant", "criterion_id", "expected", "llm_status", "llm_reason", "llm_action",
                    "agree", "status_agree", "base_llm", "llm_evidence", "llm_rationale", "edit_note", "criterion_text"])
        for pid, m in M.items():
            exp = EXPECT[m["variant"]]
            s, r, act, ev, why = res[("variant", pid)]
            b = res.get(("base", pid), ("", "", "", "", ""))
            ok, sok = (s, r) == exp, s == exp[0]
            agree += ok; st_agree += sok
            w.writerow([pid, m["base_patient_id"], m["variant"], m["target_criterion"], "/".join(exp), s, r, act,
                        "Y" if ok else "", "Y" if sok else "", f"{b[0]}/{b[1]}" if b[0] else "", ev, why,
                        notes[pid][1]["note"], C[m["target_criterion"]]["original_text"][:300]])
    print(f"agree (status+reason) {agree}/{len(M)}, status only {st_agree}/{len(M)} -> {out}")


if __name__ == "__main__":
    main()
