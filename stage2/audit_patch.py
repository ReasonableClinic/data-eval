#!/usr/bin/env python3
"""Write audit decisions (audit_dev_missing.csv) into a copy of review.csv, so apply_review.py can rebuild gold.

The audit looked at gold rows that were UNKNOWN / MISSING ("the record never mentions it") and found ones where the
record does settle the criterion. Each audit row has a tier:
  1_explicit  the record names the condition and denies it, or plainly shows it (apply)
  2_blanket   "No other cardiac, pulmonary, ... history" covers a chronic diagnosis in a named system (team rule, 6.3)
  3_inferred  follows from a reconciled medication list / complete treatment history, not stated in words
  reject      audit proposal rejected on review
Optional columns `reason` and `action` set review_reason / review_action (needed when proposed is UNKNOWN).

Usage:
  python3 audit_patch.py --review runs/dev_v3/review.csv --audit runs/audit_dev_missing.csv --tiers 1_explicit 2_blanket \
      --out runs/dev_v4/review.csv
Then run apply_review.py with --review runs/dev_v4/review.csv --accept-agreed.
"""
import argparse, csv, os

ap = argparse.ArgumentParser()
ap.add_argument("--review", required=True)
ap.add_argument("--audit", required=True)
ap.add_argument("--tiers", nargs="+", default=["1_explicit", "2_blanket"])
ap.add_argument("--out", required=True)
ap.add_argument("--force", action="store_true", help="also overwrite rows a reviewer already set (gold corrections)")
a = ap.parse_args()

fixes = {}
with open(a.audit, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["tier"] in a.tiers:
            fixes[(r["patient_id"], r["criterion_id"])] = r

with open(a.review, encoding="utf-8-sig", newline="") as f:
    rd = csv.DictReader(f)
    fields, rows = rd.fieldnames, list(rd)

done = set()
for r in rows:
    k = (r["patient_id"], r["criterion_id"])
    if k not in fixes:
        continue
    x = fixes[k]
    if not a.force and r["review_status"].strip().upper() not in ("", "OK", "UNKNOWN"):
        print(f"skip {k}: reviewer already set {r['review_status']}")
        continue
    r["review_status"] = x["proposed"]
    r["review_reason"] = x.get("reason", "") or ""
    r["review_action"] = x.get("action", "") or ""
    r["review_evidence"] = x["evidence"]
    old = r["review_note"].strip()
    r["review_note"] = (old + " / " if old else "") + f"audit 2026-10-06 tier {x['tier']}: {x['note']}"
    done.add(k)

missing = set(fixes) - done
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print(f"{len(done)} rows patched ({', '.join(a.tiers)}) -> {a.out}")
for k in sorted(missing):
    print("not found in review.csv:", k)
