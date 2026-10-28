#!/usr/bin/env python3
"""Compare the LLM labeler's trial labels with TREC 2021 qrels (proposal 6: labeler validation, trial level).

TREC has two judged labels: eligible (qrels 2) and excluded (qrels 1 = inclusion met, an exclusion criterion applies,
stored as "ineligible"). Our labeler also outputs "potential", so the script reports:
  - the full 2 x 3 table (qrels x ours)
  - Cohen's kappa three ways: potential dropped, potential counted as eligible, potential counted as ineligible
  - for qrels "ineligible": whether our ineligible came from an exclusion FAIL (the TREC meaning) or something else

Usage (trec_eval folder):
  python3 compare_trec.py --run runs/trec_v1 --qrels qrels_sample.jsonl --criteria criteria.jsonl
Writes <run>/trec_compare.json and <run>/trec_disagreements.csv.
"""
import argparse, collections, csv, json, os


def load(p):
    return [json.loads(line) for line in open(p, encoding="utf-8")] if os.path.exists(p) else []


def kappa(pairs):
    """Cohen's kappa for a list of (a, b) labels."""
    n = len(pairs)
    if not n:
        return None
    labels = sorted({x for p in pairs for x in p})
    po = sum(a == b for a, b in pairs) / n
    ca, cb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(ca[l] * cb[l] for l in labels) / (n * n)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def summarize(name, gold, ours, crit_type):
    keys = [k for k in gold if k in ours]
    table = collections.Counter((gold[k]["trial_label"], ours[k]["trial_label"]) for k in keys)
    pairs = [(gold[k]["trial_label"], ours[k]["trial_label"]) for k in keys]
    no_pot = [(a, b) for a, b in pairs if b != "potential"]
    as_el = [(a, "eligible" if b == "potential" else b) for a, b in pairs]
    as_in = [(a, "ineligible" if b == "potential" else b) for a, b in pairs]
    why = collections.Counter()
    for k in keys:
        if gold[k]["trial_label"] == "ineligible" and ours[k]["trial_label"] == "ineligible":
            fails = [c for c in ours[k]["criteria"] if c["expected_status"] == "FAIL"]
            kinds = {crit_type.get(c["criterion_id"], "inclusion") for c in fails}
            why["exclusion FAIL (TREC meaning)" if "exclusion" in kinds else
                "inclusion FAIL only" if fails else "age/sex outside range"] += 1
    return {
        "run": name, "pairs": len(keys),
        "table": {f"qrels {a} / ours {b}": table[(a, b)] for a in ("eligible", "ineligible")
                  for b in ("eligible", "potential", "ineligible")},
        "ours_potential": sum(b == "potential" for _, b in pairs),
        "accuracy_without_potential": round(sum(a == b for a, b in no_pot) / len(no_pot), 3) if no_pot else None,
        "kappa_without_potential": kappa(no_pot), "n_without_potential": len(no_pot),
        "kappa_potential_as_eligible": kappa(as_el),
        "kappa_potential_as_ineligible": kappa(as_in),
        "qrels_ineligible_and_ours_ineligible_because": dict(why),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--qrels", required=True)
    ap.add_argument("--criteria", required=True)
    a = ap.parse_args()
    gold = {(g["patient_id"], g["trial_id"]): g for g in load(a.qrels)}
    crit = {c["criterion_id"]: c for c in load(a.criteria)}
    crit_type = {k: ("exclusion" if c["type"] == "exclusion" else "inclusion") for k, c in crit.items()}
    runs = {name: {(g["patient_id"], g["trial_id"]): g for g in load(os.path.join(a.run, f))}
            for name, f in (("run1", "gold_draft.jsonl"), ("run2", "gold_draft.run2.jsonl"))}
    res = [summarize(n, gold, r, crit_type) for n, r in runs.items() if r]
    if len(res) == 2:
        both = [k for k in runs["run1"] if k in runs["run2"]]
        res.append({"run1_vs_run2_trial_label_agreement":
                    round(sum(runs["run1"][k]["trial_label"] == runs["run2"][k]["trial_label"] for k in both) / len(both), 3)})
    json.dump(res, open(os.path.join(a.run, "trec_compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in res:
        print(json.dumps(r, ensure_ascii=False, indent=1))

    r1 = runs.get("run1", {})
    out = os.path.join(a.run, "trec_disagreements.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["patient_id", "trial_id", "qrels", "ours_run1", "ours_run2", "fail_or_open_criteria"])
        for k, g in gold.items():
            o = r1.get(k)
            if not o or o["trial_label"] == g["trial_label"]:
                continue
            o2 = runs.get("run2", {}).get(k)
            key = [c for c in o["criteria"] if c["expected_status"] in ("FAIL", "CONFLICT") or
                   (c["expected_status"] == "UNKNOWN" and o["trial_label"] == "potential")]
            w.writerow([k[0], k[1], g["trial_label"], o["trial_label"], o2["trial_label"] if o2 else "",
                        " || ".join(f"{c['criterion_id']} {c['expected_status']}/{c['reason']}: "
                                    f"{crit.get(c['criterion_id'], {}).get('original_text', '')[:150]}" for c in key[:6])])
    print(f"disagreements -> {out}")


if __name__ == "__main__":
    main()
