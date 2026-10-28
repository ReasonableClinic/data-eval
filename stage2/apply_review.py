#!/usr/bin/env python3
"""Merge a reviewed review.csv back into ④ gold.

Review columns (leave empty = not reviewed yet):
  review_status   OK (accept the LLM row) | PASS | FAIL | UNKNOWN | CONFLICT | N/A (criterion does not apply)
  review_reason   needed only for UNKNOWN (MISSING / EXPIRED / UNSUPPORTED); otherwise filled automatically
  review_action   needed for UNKNOWN / CONFLICT if different from the LLM's (PASS / FAIL -> none)
  review_evidence replaces the evidence: "doc_id: exact quote | doc_id: exact quote"  (empty = keep LLM evidence)
  review_note     free text, kept in gold_review_log.jsonl
  Each gold criterion gets "review": "human" (reviewed row), "agreed" (blank row accepted by --accept-agreed because
  both runs agreed) or "llm" (blank row that still needs review).
  review_flag     "clinician" = reviewer could not decide (review page "모르겠음" button); the pair stays label_source "llm"
                  until a clinician confirms and the flag is cleared
  admin           Y = administrative criterion (consent, willingness, ...); it does not block 'eligible' when UNKNOWN/MISSING

A pair becomes label_source "human_verified" only when every one of its rows has a review_status
(with --accept-agreed: every row that needed checking; rows where both runs agreed count as accepted).

Usage:
  python3 apply_review.py --draft gold_draft.jsonl --review review.csv --patients patients.jsonl [...] \
      --trials trials.jsonl --out gold.jsonl
Writes gold.jsonl, ranking_gold.jsonl and gold_review_log.jsonl next to --out. Exit code 1 on row errors.
"""
import argparse, csv, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_lib as G  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--review", required=True)
    ap.add_argument("--patients", nargs="+", required=True)
    ap.add_argument("--trials", required=True)
    ap.add_argument("--out", default="gold.jsonl")
    ap.add_argument("--accept-agreed", action="store_true",
                    help="rows left blank that did not need checking (both runs agree, no CHECK flag, no FAIL) count as accepted; "
                         "the review page hides these rows by default")
    a = ap.parse_args()

    patients = {p["patient_id"]: p for p in G.load_jsonl(a.patients)}
    trials = {t["trial_id"]: t for t in G.load_jsonl(a.trials)}
    drafts = {(g["patient_id"], g["trial_id"]): g for g in G.load_jsonl(a.draft)}
    rows = {}
    with open(a.review, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault((r["patient_id"], r["trial_id"]), []).append(r)

    errors, warns, log, golds = [], [], [], []
    n_flag_pairs = 0
    n_accepted = 0
    for key, g in drafts.items():
        p = patients[key[0]]
        ev_by_id = {e["gold_ev_id"]: e for e in g["gold_evidence"]}
        llm = {c["criterion_id"]: c for c in g["criteria"]}
        out_crit, quotes, all_reviewed, pair_errors, flags = [], {}, True, [], []
        for r in rows.get(key, []):
            cid, rs = r["criterion_id"], r["review_status"].strip().upper()
            if (r.get("review_flag") or "").strip():
                flags.append(cid)
                log.append({"pair": key, "criterion_id": cid, "change": "FLAG clinician", "note": r["review_note"]})
            origin = "human" if rs else "llm"     # per-criterion provenance -> gold criteria[].review
            if not rs:
                needs = bool(r["check"].strip()) or "FAIL" in (r["llm_status"], r.get("llm2_status", "")) or \
                    (r.get("trial_label_llm2") and r["trial_label_llm"] != r["trial_label_llm2"])
                if a.accept_agreed and not needs:
                    n_accepted += 1
                    origin = "agreed"
                else:
                    all_reviewed = False
                rs = "OK"
            if rs == "OK":
                if r["llm_status"] == "N/A":
                    continue
                c = dict(llm[cid])
                quotes[cid] = [{"doc_id": ev_by_id[i]["doc_id"], "quote": ev_by_id[i]["text"]} for i in c["supporting_evidence"]]
            elif rs == "N/A":
                log.append({"pair": key, "criterion_id": cid, "change": "N/A", "note": r["review_note"]})
                continue
            else:
                reason = r["review_reason"].strip().upper() or G.DEFAULT_REASON.get(rs) or (llm.get(cid) or {}).get("reason")
                action = "none" if rs in ("PASS", "FAIL") else (r["review_action"].strip() or (llm.get(cid) or {}).get("expected_action"))
                c = {"criterion_id": cid, "expected_status": rs, "reason": reason, "supporting_evidence": [],
                     "decoy_evidence": [], "expected_action": action}
                old = llm.get(cid)
                quotes[cid] = ([{"doc_id": ev_by_id[i]["doc_id"], "quote": ev_by_id[i]["text"]} for i in old["supporting_evidence"]]
                               if old else [])
                log.append({"pair": key, "criterion_id": cid, "change": f"{r['llm_status']}/{r['llm_reason']} -> {rs}/{reason}",
                            "note": r["review_note"]})
            if r["review_evidence"].strip():
                quotes[cid] = [{"doc_id": part.split(":", 1)[0].strip(), "quote": part.split(":", 1)[1].strip()}
                               for part in r["review_evidence"].split(" | ") if ":" in part]
            if (c["expected_status"], c["reason"]) not in G.NEEDS_EVIDENCE and not r["review_evidence"].strip():
                quotes[cid] = []                                  # e.g. UNKNOWN/MISSING carries no evidence
            pair_errors += [f"{key[0]} x {key[1]} {p_}" for p_ in G.check_criterion(c)]
            c["review"] = origin
            out_crit.append(c)
        ev_input = [{"criterion_id": c["criterion_id"], "evidence": quotes.get(c["criterion_id"], [])} for c in out_crit]
        gold_ev, per, qprobs = G.build_gold_evidence(ev_input, p)
        pair_errors += [f"{key[0]} x {key[1]} {q}" for q in qprobs]
        for c in out_crit:
            c["supporting_evidence"] = per.get(c["criterion_id"], [])
            if (c["expected_status"], c["reason"]) in G.NEEDS_EVIDENCE and not c["supporting_evidence"]:
                pair_errors.append(f"{key[0]} x {key[1]} {c['criterion_id']}: {c['expected_status']}/{c['reason']} without evidence")
        # fully reviewed pairs must be clean; unreviewed pairs only get warnings
        (errors if all_reviewed and rows.get(key) else warns).extend(pair_errors)
        verified = all_reviewed and bool(rows.get(key)) and not pair_errors and not flags
        n_flag_pairs += bool(flags)
        ng = dict(g, criteria=out_crit, gold_evidence=gold_ev,
                  label_source="human_verified" if verified else "llm",
                  trial_label=G.trial_label(out_crit,
                                            G.structured_check(p, trials[g["trial_id"]]),
                                            # "admin" column of review.csv (Y = administrative); reviewers may change it
                                            frozenset(r["criterion_id"] for r in rows.get(key, [])
                                                      if (r.get("admin") or "").strip().upper() in ("Y", "YES", "1", "TRUE"))))
        golds.append(ng)

    out_dir = os.path.dirname(os.path.abspath(a.out))
    G.write_jsonl(a.out, golds)
    G.write_jsonl(os.path.join(out_dir, "ranking_gold.jsonl"), G.ranking_rows(golds, trials))
    G.write_jsonl(os.path.join(out_dir, "gold_review_log.jsonl"), [dict(x, pair=list(x["pair"])) for x in log])
    n_h = sum(g["label_source"] == "human_verified" for g in golds)
    for e in errors:
        print("ERROR", e)
    if warns:
        print(f"WARN  {len(warns)} problems in pairs not fully reviewed yet (they stay label_source 'llm')")
    if a.accept_agreed:
        print(f"INFO  {n_accepted} blank rows accepted because both runs agreed and nothing was flagged")
    if n_flag_pairs:
        print(f"FLAG  {n_flag_pairs} pairs have criteria marked for clinician confirmation (they stay label_source 'llm')")
    print(f"{len(golds)} pairs -> {a.out} ({n_h} human_verified, {len(golds) - n_h} still llm), {len(log)} changes, {len(errors)} errors")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
