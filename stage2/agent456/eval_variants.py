#!/usr/bin/env python3
"""Score an agent's criterion judgments on the dev variant set (Agent 3 / 4 / 5) and, optionally, rankings (Agent 6).

Input (--pred): one JSON line per patient-trial pair, like agent3_out.jsonl:
  {"patient_id", "trial_id", "trial_label", "criteria": [{"criterion_id", "status", "reason", "action"}]}
  (also accepted: expected_status / expected_action, or one line per criterion with patient_id + trial_id + criterion_id)
It must cover the variant patients (input/patients_variants.jsonl); base patients are optional but needed for --base.

Reports
  1. variant targets: per variant type, how often the target criterion gets the injected status (and reason, action)
  2. confirmed judgments (PASS/FAIL reviewed by a person or agreed by two runs, targets excluded):
     how many the agent turned into UNKNOWN/CONFLICT ("downgraded") or flipped PASS<->FAIL  -> Agent 4 must keep these low
  3. trial labels of the variant pairs whose label changed because of the injection
  4. --ranking FILE (Agent 6): {"patient_id", "ranking": [trial_id, ...]} per line, compared with gold/ranking_gold*.jsonl
Usage:
  python3 eval/eval_variants.py --data dev --pred my_run/out.jsonl [--ranking my_run/ranking.jsonl] [--csv my_run/eval_rows.csv]
"""
import argparse, collections, csv, json, os

AC_OK = {"UNKNOWN": None, "CONFLICT": "clinician_confirmation"}


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def first(d, *ks):
    for k in ks:
        if d.get(k) not in (None, ""):
            return d[k]
    return ""


def read_pred(path):
    pred, labels = {}, {}
    for line in jl(path):
        pk = (line.get("patient_id"), line.get("trial_id"))
        if line.get("trial_label"):
            labels[pk] = line["trial_label"]
        rows = line.get("criteria") if isinstance(line.get("criteria"), list) else ([line] if line.get("criterion_id") else [])
        for c in rows:
            pred[pk + (c["criterion_id"],)] = (first(c, "status", "expected_status"), first(c, "reason"), first(c, "action", "expected_action"))
    return pred, labels


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="dev", help="folder with input/ gold/ (default: dev)")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--ranking")
    ap.add_argument("--csv", help="write one row per scored criterion")
    a = ap.parse_args()
    GV = jl(os.path.join(a.data, "gold", "gold_variants.jsonl"))
    GB = jl(os.path.join(a.data, "gold", "gold.jsonl"))
    pred, labels = read_pred(a.pred)
    out_rows = []

    # 1. targets
    by = collections.defaultdict(collections.Counter)
    for g in GV:
        inj = g.get("injection") or {}
        if not inj.get("doc_id"):
            continue
        c = next(x for x in g["criteria"] if x["criterion_id"] == inj["target_criterion"])
        v = inj["variant"]
        p = pred.get((g["patient_id"], g["trial_id"], c["criterion_id"]))
        by[v]["n"] += 1
        if p is None:
            by[v]["missing_pred"] += 1
            continue
        st, rs, ac = p
        by[v]["status"] += st == c["expected_status"]
        by[v]["status+reason"] += (st, rs) == (c["expected_status"], c["reason"])
        by[v]["action"] += ac == c["expected_action"]
        if c["expected_status"] in ("UNKNOWN", "CONFLICT") and st in ("PASS", "FAIL"):
            by[v]["decided_instead"] += 1
        out_rows.append(["target", v, g["patient_id"], g["trial_id"], c["criterion_id"], f"{c['expected_status']}/{c['reason']}/{c['expected_action']}", f"{st}/{rs}/{ac}"])
    print("1. variant targets (injected criterion)")
    print(f"   {'type':12} {'n':>3} {'status':>7} {'st+reason':>9} {'action':>7} {'decided':>8} {'no pred':>8}")
    for v in ("violation", "missing", "expired", "conflict", "unsupported"):
        x = by.get(v)
        if not x:
            continue
        n = x["n"]
        print(f"   {v:12} {n:>3} {x['status']:>7} {x['status+reason']:>9} {x['action']:>7} {x['decided_instead']:>8} {x['missing_pred']:>8}")
    print("   (decided = expected UNKNOWN/CONFLICT but the agent gave PASS/FAIL)")

    # 2. confirmed judgments
    cnt = collections.Counter()
    for src, gs in (("base", GB), ("variant", GV)):
        for g in gs:
            tgt = (g.get("injection") or {}).get("target_criterion") if (g.get("injection") or {}).get("doc_id") else None
            for c in g["criteria"]:
                if c["criterion_id"] == tgt or c["expected_status"] not in ("PASS", "FAIL") or c.get("review") not in ("human", "agreed"):
                    continue
                p = pred.get((g["patient_id"], g["trial_id"], c["criterion_id"]))
                if p is None:
                    continue
                cnt[src + " n"] += 1
                if p[0] in ("UNKNOWN", "CONFLICT"):
                    cnt[src + " downgraded"] += 1
                    out_rows.append(["downgraded", src, g["patient_id"], g["trial_id"], c["criterion_id"], c["expected_status"], "/".join(p)])
                elif p[0] != c["expected_status"] and p[0] in ("PASS", "FAIL"):
                    cnt[src + " flipped"] += 1
                    out_rows.append(["flipped", src, g["patient_id"], g["trial_id"], c["criterion_id"], c["expected_status"], "/".join(p)])
    print("\n2. confirmed PASS/FAIL (targets excluded)")
    for src in ("base", "variant"):
        n = cnt[src + " n"]
        if n:
            print(f"   {src:8} n={n}: downgraded to UNKNOWN/CONFLICT {cnt[src + ' downgraded']} ({cnt[src + ' downgraded'] / n:.1%}), "
                  f"flipped PASS<->FAIL {cnt[src + ' flipped']}")

    # 3. trial labels that the injection changed
    base_label = {(g["patient_id"], g["trial_id"]): g["trial_label"] for g in GB}
    pm = {}
    mp = os.path.join(a.data, "eval", "update_pairs.csv")
    if os.path.exists(mp):
        pm = {r["variant_patient_id"]: r["base_patient_id"] for r in csv.DictReader(open(mp, encoding="utf-8-sig"))}
    ch = ok = 0
    for g in GV:
        b = base_label.get((pm.get(g["patient_id"]), g["trial_id"]))
        if b and b != g["trial_label"] and (g["patient_id"], g["trial_id"]) in labels:
            ch += 1
            ok += labels.get((g["patient_id"], g["trial_id"])) == g["trial_label"]
    if ch:
        print(f"\n3. trial label changed by the injection: {ch} pairs, agent label right {ok}/{ch}")

    # 4. ranking
    if a.ranking:
        R = {r["patient_id"]: r["ranking"] for r in jl(a.ranking)}
        exact = top1 = n = 0
        for f in ("ranking_gold.jsonl", "ranking_gold_variants.jsonl"):
            for r in jl(os.path.join(a.data, "gold", f)):
                if r["patient_id"] not in R:
                    continue
                n += 1
                exact += R[r["patient_id"]] == r["ranking"]
                top1 += (R[r["patient_id"]][:1] == r["ranking"][:1])
        print(f"\n4. ranking: {n} patients, exact order {exact}, same first trial {top1}")
    if a.csv:
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["kind", "group", "patient_id", "trial_id", "criterion_id", "gold", "pred"])
            w.writerows(out_rows)
        print(f"\nrows -> {a.csv}")


if __name__ == "__main__":
    main()
