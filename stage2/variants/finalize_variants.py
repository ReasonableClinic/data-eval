#!/usr/bin/env python3
"""Step 4: freeze a checked variant set into final_<split>/ (2026-10-23).
Target criterion `review`: "agreed" when the blind LLM check matched, "human" when a person reviewed the disagreement
(all reviewed rows kept the variant gold; conflicts stay CONFLICT per common format 6.3).
Writes final_<split>/patients_variants.jsonl, gold_variants.jsonl, pairs_variants.jsonl (input pairs, no answers),
id_map_variants_private.json.
Usage: python3 finalize_variants.py --split dev --dir out_dev
"""
import argparse, csv, json, os, collections
ap = argparse.ArgumentParser(); ap.add_argument("--split", required=True); ap.add_argument("--dir", required=True); a = ap.parse_args()
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731
M = json.load(open(os.path.join(a.dir, "id_map_variants.json")))
rep = {r["patient_id"]: r for r in csv.DictReader(open(os.path.join(a.dir, "verify_report.csv"), encoding="utf-8-sig"))}
G = jl(os.path.join(a.dir, "gold_variants.jsonl"))
st = collections.Counter()
for g in G:
    t = M[g["patient_id"]]["target_criterion"]
    for c in g["criteria"]:
        if c["criterion_id"] == t and (g.get("injection") or {}).get("doc_id"):
            r = rep.get(g["patient_id"])
            c["review"] = "agreed" if r and r["agree"] == "Y" and M[g["patient_id"]]["variant"] == r["variant"] else "human"
            st[c["review"]] += 1
out = os.path.join(os.path.dirname(os.path.abspath(a.dir)), f"final_{a.split}")
os.makedirs(out, exist_ok=True)
P = jl(os.path.join(a.dir, "patients_variants.jsonl"))
w = lambda n, rows: open(os.path.join(out, n), "w", encoding="utf-8").writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in rows)  # noqa: E731
w("patients_variants.jsonl", P)
w("gold_variants.jsonl", G)
pairs = collections.defaultdict(list)
for g in G:
    pairs[g["patient_id"]].append(g["trial_id"])
w("pairs_variants.jsonl", [{"patient_id": k, "trial_ids": v} for k, v in pairs.items()])
json.dump(M, open(os.path.join(out, "id_map_variants_private.json"), "w"), indent=1)
print(f"{a.split}: {len(P)} patients, {len(G)} pairs, targets {dict(st)} -> {out}")
print(collections.Counter(m["variant"] for m in M.values()), collections.Counter(g["trial_label"] for g in G))
