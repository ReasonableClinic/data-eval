#!/usr/bin/env python3
"""Structural checks for a built variant set (run after build_variants.py).
- exactly one document differs from the base patient (or one new document); summary unchanged
- every gold evidence span matches its document text; document dates <= as_of
- only the target criterion differs from the base gold; judgments that need evidence have it
Usage: python3 check_variants.py --split dev --dir out_dev
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import gold_lib as G  # noqa: E402
ROOT = os.path.join(HERE, "..", "..")
SETS = {"dev": ("patients_v2.jsonl", "stage2/runs/dev_v10"), "test": ("patients_eval_v2.jsonl", "stage2/runs/test_v9")}
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731
ap = argparse.ArgumentParser(); ap.add_argument("--split", required=True); ap.add_argument("--dir", required=True); a = ap.parse_args()
pf, run = SETS[a.split]
P = {p["patient_id"]: p for p in jl(os.path.join(ROOT, pf))}
GB = {(g["patient_id"], g["trial_id"]): g for g in jl(os.path.join(ROOT, run, "gold.jsonl"))}
V = {p["patient_id"]: p for p in jl(os.path.join(a.dir, "patients_variants.jsonl"))}
GV = jl(os.path.join(a.dir, "gold_variants.jsonl"))
M = json.load(open(os.path.join(a.dir, "id_map_variants.json")))
errs = []
for pid, vp in V.items():
    base = P[M[pid]["base_patient_id"]]
    pre = base["patient_id"]
    if vp["summary"] != base["summary"] or vp["as_of"] != base["as_of"]:
        errs.append(f"{pid}: summary/as_of changed")
    bd = {d["doc_id"].replace(pre + "-", pid + "-", 1): d for d in base["documents"]}
    key = lambda d: (d["text"], d["date"], d["type"], d["author_role"])  # noqa: E731
    base_keys = [key(d) for d in base["documents"]]
    changed = [d["doc_id"] for d in vp["documents"] if key(d) not in base_keys]   # matched by content: ids follow date order
    if [d["doc_id"] for d in vp["documents"]] != [f"{pid}-D{i:02d}" for i in range(1, len(vp["documents"]) + 1)]:
        errs.append(f"{pid}: doc ids not in document order")
    if len(changed) != 1 or len(vp["documents"]) - len(bd) not in (0, 1):
        errs.append(f"{pid}: {len(changed)} documents changed {changed}")
    if any(d["date"] > vp["as_of"] for d in vp["documents"]):
        errs.append(f"{pid}: document after as_of")
    if any(not d["doc_id"].startswith(pid + "-") for d in vp["documents"]):
        errs.append(f"{pid}: doc id prefix")
for g in GV:
    pid = g["patient_id"]; vp = V[pid]; docs = {d["doc_id"]: d["text"] for d in vp["documents"]}
    base = GB[(M[pid]["base_patient_id"], g["trial_id"])]
    for x in g["gold_evidence"]:
        s, e = x["span"]
        if docs.get(x["doc_id"], "")[s:e] != x["text"]:
            errs.append(f"{pid} {g['trial_id']} {x['gold_ev_id']}: span mismatch")
    bc = {c["criterion_id"]: c for c in base["criteria"]}
    for c in g["criteria"]:
        b = bc[c["criterion_id"]]
        same = (c["expected_status"], c["reason"], c["expected_action"]) == (b["expected_status"], b["reason"], b["expected_action"])
        if c["criterion_id"] == M[pid]["target_criterion"]:
            if same:
                errs.append(f"{pid} {c['criterion_id']}: target unchanged")
        elif not same:
            errs.append(f"{pid} {c['criterion_id']}: non-target criterion changed")
        if (c["expected_status"], c["reason"]) in G.NEEDS_EVIDENCE and not c["supporting_evidence"]:
            errs.append(f"{pid} {c['criterion_id']}: {c['expected_status']}/{c['reason']} without evidence")
print(f"{len(V)} variant patients, {len(GV)} pairs checked; {len(errs)} problems")
for x in errs:
    print("  ", x)
