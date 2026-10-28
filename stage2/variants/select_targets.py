#!/usr/bin/env python3
"""Step 1 of the variant set (common format ch. 7): choose one target criterion per variant type per base patient.

Target pool: gold PASS rows reviewed by a person, structured ①-b, not administrative, not in a multi-line
logic_group, with supporting evidence in ONE document whose spans no other criterion of this patient cites
(so the edit changes exactly one gold criterion). `expired` also needs a time_window and a document that no
other time-windowed criterion of this patient cites (its date moves).

Usage (stage2/variants):
  python3 select_targets.py --split dev --out plan_dev.json      # plan + context for writing the edits
"""
import argparse, collections, csv, json, random, re, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import gold_lib as G  # noqa: E402

ROOT = os.path.join(HERE, "..", "..")
SETS = {"dev": ("patients_v2.jsonl", "stage2/runs/dev_v10", "ctgov_v2/dev/criteria.jsonl"),
        "test": ("patients_eval_v2.jsonl", "stage2/runs/test_v9", "ctgov_v2/test/criteria.jsonl")}
NUM = {">", ">=", "<", "<=", "between"}
# demographics: one edit would change every trial of the patient (age/sex are also checked structurally)
SKIP_CONCEPTS = {"age", "sex", "birth_date", "pregnancy", "childbearing_potential", "menopausal_status", "nationality"}
IF_APPLICABLE = re.compile(r"\bif (applicable|any|present|relevant)\b|\bif (?:the )?(?:patient|participant|subject)s? (?:is|are|has|have)", re.I)
EXPIRE_MARGIN = 21   # days past the window
TYPES = ["violation", "missing", "expired", "conflict", "unsupported"]


def jl(p):
    return [json.loads(l) for l in open(os.path.join(ROOT, p), encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=SETS, required=True)
    ap.add_argument("--seed", type=int, default=20261023)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pf, run, cf = SETS[a.split]
    P = {p["patient_id"]: p for p in jl(pf)}
    C = {c["criterion_id"]: c for c in jl(cf)}
    GD = jl(f"{run}/gold.jsonl")
    admin = collections.defaultdict(set)
    with open(os.path.join(ROOT, run, "review.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("admin") or "").strip().upper() in ("Y", "YES", "1", "TRUE"):
                admin[(r["patient_id"], r["trial_id"])].add(r["criterion_id"])

    use = collections.defaultdict(set)          # (pid, doc, span) -> {(trial, crit)}
    doc_tw = collections.defaultdict(set)       # (pid, doc) -> time-windowed criteria citing it
    for g in GD:
        E = {e["gold_ev_id"]: e for e in g["gold_evidence"]}
        for c in g["criteria"]:
            for i in c["supporting_evidence"] + c.get("decoy_evidence", []):
                e = E[i]
                use[(g["patient_id"], e["doc_id"], tuple(e["span"]))].add((g["trial_id"], c["criterion_id"]))
                if C.get(c["criterion_id"], {}).get("time_window"):
                    doc_tw[(g["patient_id"], e["doc_id"])].add((g["trial_id"], c["criterion_id"]))

    by_doc = collections.defaultdict(list)
    for (pid, doc, span), who in use.items():
        by_doc[(pid, doc)].append((span, who))

    def cited_by(pid, e):
        """criteria citing any span that overlaps this evidence (same sentence quoted twice counts)"""
        s0, e0 = e["span"]
        out = set()
        for (s1, e1), who in by_doc[(pid, e["doc_id"])]:
            if s1 < e0 and s0 < e1:
                out |= who
        return out

    cands = collections.defaultdict(lambda: collections.defaultdict(list))
    for g in GD:
        pid, E = g["patient_id"], {e["gold_ev_id"]: e for e in g["gold_evidence"]}
        for c in g["criteria"]:
            cid = c["criterion_id"]
            cr = C.get(cid, {})
            if c["expected_status"] != "PASS" or c.get("review") not in ("agreed", "human"):
                continue
            if cr.get("parse_status") != "structured" or cr.get("administrative") or cid in admin[(pid, g["trial_id"])]:
                continue
            if cr.get("logic_group") or (cr.get("original_text") or "").rstrip(" :;,").lower().endswith(" or"):
                continue
            ev = [E[i] for i in c["supporting_evidence"]]
            docs = {e["doc_id"] for e in ev}
            if not ev or len(docs) != 1:
                continue
            if any(cited_by(pid, e) != {(g["trial_id"], cid)} for e in ev):
                continue
            if cr.get("concept") in SKIP_CONCEPTS or IF_APPLICABLE.search(cr.get("original_text") or ""):
                continue
            item = {"trial_id": g["trial_id"], "criterion_id": cid, "ev": c["supporting_evidence"]}
            op = cr.get("operator")
            if op in NUM or op in ("exists", "not_exists"):
                cands[pid]["violation"].append(dict(item, numeric=op in NUM))
            cands[pid]["missing"].append(item)
            if op in ("exists", "not_exists"):
                cands[pid]["conflict"].append(item)
                cands[pid]["unsupported"].append(item)
            tw = cr.get("time_window") or {}
            if tw.get("anchor") == "as_of" and tw.get("max_days_before"):
                doc = next(iter(docs))
                ddate = next(d["date"] for d in P[pid]["documents"] if d["doc_id"] == doc)
                age = (G.date.fromisoformat(P[pid]["as_of"]) - G.date.fromisoformat(ddate)).days
                new_age = tw["max_days_before"] + EXPIRE_MARGIN
                others = [C[o]["time_window"] for _, o in doc_tw[(pid, doc)] - {(g["trial_id"], cid)}]
                # move the document just past the target's window; every other time-windowed criterion citing
                # this document must still be inside its own window at the new date
                if age <= tw["max_days_before"] and all(o.get("anchor") == "as_of" and (o.get("max_days_before") or 10 ** 6) >= new_age
                                                        and not o.get("min_days_before") for o in others):
                    cands[pid]["expired"].append(dict(item, new_age_days=new_age))

    # prefer targets in trials that are not already ineligible, so the trial label can change too
    LABEL_RANK = {"eligible": 0, "potential": 1, "ineligible": 2}
    label = {(g["patient_id"], g["trial_id"]): g["trial_label"] for g in GD}
    rnd = random.Random(a.seed)
    plan = []
    for pid in sorted(cands):
        used_c, used_t = set(), collections.Counter()
        for t in ["expired", "violation", "conflict", "unsupported", "missing"]:   # scarcest first
            pool = [x for x in cands[pid][t] if x["criterion_id"] not in used_c]
            if not pool:
                continue
            rnd.shuffle(pool)
            pool.sort(key=lambda x: (LABEL_RANK[label[(pid, x["trial_id"])]], not x.get("numeric", False) if t == "violation" else 0, used_t[x["trial_id"]]))
            x = pool[0]
            alts = [y["criterion_id"] for y in pool[1:4]]
            used_c.add(x["criterion_id"]); used_t[x["trial_id"]] += 1
            g = next(g for g in GD if g["patient_id"] == pid and g["trial_id"] == x["trial_id"])
            E = {e["gold_ev_id"]: e for e in g["gold_evidence"]}
            p, cr = P[pid], C[x["criterion_id"]]
            evs = []
            for i in x["ev"]:
                e = E[i]
                d = next(d for d in p["documents"] if d["doc_id"] == e["doc_id"])
                s, en = e["span"]
                evs.append({"gold_ev_id": i, "doc_id": e["doc_id"], "doc_type": d["type"], "doc_date": d["date"],
                            "author_role": d["author_role"], "span": e["span"], "quote": e["text"],
                            "concept": e.get("concept"), "value": e.get("value"), "unit": e.get("unit"),
                            "context": d["text"][max(0, s - 250):en + 250]})
            extra = {"new_age_days": x["new_age_days"]} if "new_age_days" in x else {}
            plan.append({**extra, "base_patient_id": pid, "base_id": g["base_id"], "as_of": p["as_of"], "variant": t,
                         "trial_id": x["trial_id"], "criterion_id": x["criterion_id"], "criterion_type": cr["type"],
                         "original_text": cr["original_text"],
                         "parsed": {k: cr.get(k) for k in ("concept", "operator", "value", "unit", "term", "time_window",
                                                           "answerable_by")},
                         "evidence": evs, "alternates": alts})
    json.dump(plan, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(plan)} variants for {len({x['base_patient_id'] for x in plan})} base patients -> {a.out}")
    print(collections.Counter(x["variant"] for x in plan))
    missing = {pid: [t for t in TYPES if not any(x["base_patient_id"] == pid and x["variant"] == t for x in plan)]
               for pid in sorted(P)}
    print("types without a target:", {k: v for k, v in missing.items() if v})


if __name__ == "__main__":
    main()
