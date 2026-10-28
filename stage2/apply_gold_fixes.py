#!/usr/bin/env python3
"""Apply a gold_fixes CSV (patient_id, trial_id, criterion_id, old, new_status, new_reason, new_action, why) to a gold run.
Copies --run-in to --run-out, sets each criterion's status/reason/action (UNKNOWN/CONFLICT -> evidence cleared unless
--keep-evidence), review "human", fills the review.csv review_* columns with a dated note, recomputes trial labels
(admin flags from review.csv) and ranking_gold. Refuses a row whose current value differs from `old`.
Optional columns: evidence "DOC: exact quote | DOC: quote" (located in the record; an existing gold evidence entry with
the same span is reused, otherwise one is added with concept/term/value from the evidence_concept / evidence_term
columns, default procedure / true; evidence_value / evidence_unit for a measurement), used for PASS/FAIL fixes.
Usage: python3 apply_gold_fixes.py --run-in runs/dev_v8 --run-out runs/dev_v9 --fixes runs/gold_fixes_dev_1025.csv \
           --patients ../patients_v2.jsonl --date 2026-10-25
"""
import argparse, collections, csv, json, os, shutil, sys
import gold_lib as G
ap = argparse.ArgumentParser()
for k in ("--run-in", "--run-out", "--fixes", "--date"):
    ap.add_argument(k, required=True)
ap.add_argument("--patients", nargs="+", required=True)
ap.add_argument("--trials", default="../ctgov_v1/trials.jsonl")
ap.add_argument("--keep-evidence", action="store_true")
ap.add_argument("--admin-false", nargs="*", default=[], help="criterion IDs whose review.csv admin flag is cleared (①-b administrative false)")
a = ap.parse_args()
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731
P = {p["patient_id"]: p for path in a.patients for p in jl(path)}
T = {t["trial_id"]: t for t in jl(a.trials)}
F = {(r["patient_id"], r["trial_id"], r["criterion_id"]): r for r in csv.DictReader(open(a.fixes, encoding="utf-8-sig"))}
if os.path.abspath(a.run_in) == os.path.abspath(a.run_out):
    sys.exit("run-out must differ from run-in")
os.makedirs(a.run_out, exist_ok=True)
for f in os.listdir(a.run_in):
    if os.path.isfile(os.path.join(a.run_in, f)) and not os.path.exists(os.path.join(a.run_out, f)):
        shutil.copyfile(os.path.join(a.run_in, f), os.path.join(a.run_out, f))
rv_path = os.path.join(a.run_in, "review.csv")
rows = list(csv.DictReader(open(rv_path, encoding="utf-8-sig")))
fields = list(rows[0].keys())
nadm = 0
for r in rows:
    if r["criterion_id"] in a.admin_false and r.get("admin"):
        r["admin"], nadm = "", nadm + 1
admin = collections.defaultdict(set)
for r in rows:
    if (r.get("admin") or "").strip().upper() in ("Y", "YES", "1", "TRUE"):
        admin[(r["patient_id"], r["trial_id"])].add(r["criterion_id"])
golds, done, probs, lab = jl(os.path.join(a.run_in, "gold.jsonl")), set(), [], []
for g in golds:
    for c in g["criteria"]:
        k = (g["patient_id"], g["trial_id"], c["criterion_id"])
        r = F.get(k)
        if not r:
            continue
        cur = f"{c['expected_status']}/{c.get('reason')}"
        if r["old"] and cur != r["old"]:
            probs.append(f"{k}: current {cur} != old {r['old']} (skipped)")
            continue
        st = r["new_status"]
        c.update(expected_status=st, reason=r["new_reason"] or ("VALID" if st == "PASS" else "VIOLATED" if st == "FAIL" else ""),
                 expected_action=r["new_action"] or "none", review="human")
        if st in ("UNKNOWN",) and r["new_reason"] == "MISSING" and not a.keep_evidence:
            c["supporting_evidence"] = []
        if (r.get("evidence") or "").strip():
            docs = {d["doc_id"]: d for d in P[g["patient_id"]]["documents"]}
            ids = []
            for part in [x.strip() for x in r["evidence"].split(" | ") if x.strip()]:
                doc, q = [x.strip() for x in part.split(":", 1)]
                sp = G.locate(docs[doc]["text"], q) if doc in docs else None
                if not sp:
                    probs.append(f"{k}: quote not found {part[:60]}")
                    continue
                hit = next((e for e in g["gold_evidence"] if e["doc_id"] == doc and e["span"] == list(sp)), None)
                if hit is None:
                    n = max([int(e["gold_ev_id"][1:]) for e in g["gold_evidence"]] + [0]) + 1
                    ev = (r.get("evidence_value") or "").strip()
                    try:
                        ev = float(ev) if ev else True
                    except ValueError:
                        pass                                  # a word ("not detected") stays as written
                    hit = {"gold_ev_id": f"G{n:02d}", "concept": r.get("evidence_concept") or "procedure", "value": ev,
                           "unit": r.get("evidence_unit") or None,
                           "observed_date": docs[doc].get("date"), "doc_id": doc, "span": list(sp),
                           "text": docs[doc]["text"][sp[0]:sp[1]], "term": r.get("evidence_term") or None, "status": "observed"}
                    g["gold_evidence"].append(hit)
                ids.append(hit["gold_ev_id"])
            c["supporting_evidence"] = ids
        done.add(k)
    old = g["trial_label"]
    g["trial_label"] = G.trial_label(g["criteria"], G.structured_check(P[g["patient_id"]], T[g["trial_id"]]),
                                     frozenset(admin[(g["patient_id"], g["trial_id"])]))
    if old != g["trial_label"]:
        lab.append(f"{g['patient_id']} {g['trial_id']}: {old} -> {g['trial_label']}")
for r in rows:
    k = (r["patient_id"], r["trial_id"], r["criterion_id"])
    if k in done:
        f = F[k]
        r.update(review_status=f["new_status"], review_reason=f["new_reason"], review_action=f["new_action"], review_evidence=f.get("evidence") or "",
                 review_note=f"{a.date} fix: {f['why']}")
with open(os.path.join(a.run_out, "review.csv"), "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
log_in = os.path.join(a.run_in, "gold_review_log.jsonl")
shutil.copyfile(log_in, os.path.join(a.run_out, "gold_review_log.jsonl")) if os.path.exists(log_in) else None
with open(os.path.join(a.run_out, "gold_review_log.jsonl"), "a", encoding="utf-8") as fh:
    for k in sorted(done):
        fh.write(json.dumps({"pair": [k[0], k[1]], "criterion_id": k[2], "change": f"{F[k]['old']} -> {F[k]['new_status']}/{F[k]['new_reason']}",
                             "note": f"{a.date} fix: {F[k]['why']}"}, ensure_ascii=False) + "\n")
G.write_jsonl(os.path.join(a.run_out, "gold.jsonl"), golds)
G.write_jsonl(os.path.join(a.run_out, "ranking_gold.jsonl"), G.ranking_rows(golds, T))
miss = set(F) - done
print(f"{len(done)}/{len(F)} fixes applied, {nadm} admin flags cleared -> {a.run_out}; label changes {len(lab)}")
for x in lab + probs + [f"not found: {m}" for m in miss]:
    print("  ", x)
print(collections.Counter(g["trial_label"] for g in golds))
