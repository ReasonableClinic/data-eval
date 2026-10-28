#!/usr/bin/env python3
"""Apply audit tiers straight to gold.jsonl (no new LLM run) — used for A1 (2_blanket, team decision at the 3rd meeting).
Each audit row: tier, patient_id, trial_id, criterion_id, proposed (PASS/FAIL), evidence "DOC: quote | DOC: quote", note.
Evidence quotes are located in the patient's documents; an existing gold evidence entry with the same span is reused,
otherwise a new one is added (concept from the criterion's ①-b, value false for a denial, status observed).
Trial labels are recomputed (admin flags from review.csv). review.csv is updated with audit_patch.py separately.
Usage: python3 apply_audit_gold.py --run-in runs/dev_v7 --run-out runs/dev_v8 --audit runs/audit_dev_missing.csv --tiers 2_blanket \
           --patients ../patients_v2.jsonl --criteria ../ctgov_v2/dev/criteria.jsonl
"""
import argparse, collections, csv, json, os, shutil
import gold_lib as G
ap = argparse.ArgumentParser()
for k in ("--run-in", "--run-out", "--audit", "--patients", "--criteria"):
    ap.add_argument(k, required=True)
ap.add_argument("--tiers", nargs="+", required=True)
a = ap.parse_args()
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731
P = {p["patient_id"]: p for p in jl(a.patients)}
C = {c["criterion_id"]: c for c in jl(a.criteria)}
T = {t["trial_id"]: t for t in jl("../ctgov_v1/trials.jsonl")}
A = {(r["patient_id"], r["trial_id"], r["criterion_id"]): r for r in csv.DictReader(open(a.audit, encoding="utf-8-sig")) if r["tier"] in a.tiers}
os.makedirs(a.run_out, exist_ok=True)
for f in os.listdir(a.run_in):
    if not os.path.exists(os.path.join(a.run_out, f)):
        shutil.copyfile(os.path.join(a.run_in, f), os.path.join(a.run_out, f))
admin = collections.defaultdict(set)
for r in csv.DictReader(open(os.path.join(a.run_in, "review.csv"), encoding="utf-8-sig")):
    if (r.get("admin") or "").strip().upper() in ("Y", "YES", "1", "TRUE"):
        admin[(r["patient_id"], r["trial_id"])].add(r["criterion_id"])
golds, done, probs, lab = jl(os.path.join(a.run_in, "gold.jsonl")), 0, [], []
for g in golds:
    docs = {d["doc_id"]: d["text"] for d in P[g["patient_id"]]["documents"]}
    ev = g["gold_evidence"]
    for c in g["criteria"]:
        r = A.get((g["patient_id"], g["trial_id"], c["criterion_id"]))
        if not r:
            continue
        ids = []
        for part in [x.strip() for x in r["evidence"].split(" | ") if x.strip()]:
            doc, q = part.split(":", 1)
            doc, q = doc.strip(), q.strip()
            sp = G.locate(docs.get(doc, ""), q)
            if not sp:
                probs.append(f"{g['patient_id']} {c['criterion_id']}: quote not found {part[:60]}")
                continue
            hit = next((e for e in ev if e["doc_id"] == doc and e["span"] == list(sp)), None)
            if hit is None:
                n = max([int(e["gold_ev_id"][1:]) for e in ev] + [0]) + 1
                cr = C.get(c["criterion_id"], {})
                term = cr.get("term")
                hit = {"gold_ev_id": f"G{n:02d}", "concept": cr.get("concept") or "diagnosis", "value": r["proposed"] != "PASS",
                       "unit": None, "observed_date": None, "doc_id": doc, "span": list(sp), "text": docs[doc][sp[0]:sp[1]],
                       "status": "observed", "term": (term[0] if isinstance(term, list) and term else term)}
                ev.append(hit)
            ids.append(hit["gold_ev_id"])
        if not ids:
            continue
        st = r["proposed"]
        c.update(expected_status=st, reason="VALID" if st == "PASS" else "VIOLATED", expected_action="none",
                 supporting_evidence=ids, review="human")
        done += 1
    old = g["trial_label"]
    g["trial_label"] = G.trial_label(g["criteria"], G.structured_check(P[g["patient_id"]], T[g["trial_id"]]), frozenset(admin[(g["patient_id"], g["trial_id"])]))
    if old != g["trial_label"]:
        lab.append(f"{g['patient_id']} {g['trial_id']}: {old} -> {g['trial_label']}")
open(os.path.join(a.run_out, "gold.jsonl"), "w", encoding="utf-8").writelines(json.dumps(g, ensure_ascii=False) + "\n" for g in golds)
rk = G.ranking_rows(golds, T)
open(os.path.join(a.run_out, "ranking_gold.jsonl"), "w", encoding="utf-8").writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rk)
print(f"{done}/{len(A)} criteria patched -> {a.run_out}; label changes {len(lab)}")
for x in lab + probs:
    print("  ", x)
print(collections.Counter(g["trial_label"] for g in golds))
