#!/usr/bin/env python3
"""Step 2 of the variant set (common format ch. 7): apply hand-written record edits and build variant patients + gold.

edits_<split>.json: list of
  {"base": "SYN-0001", "variant": "violation|missing|expired|conflict|unsupported", "criterion_id": "...",
   "doc_id": "SYN-0001-D08" | "NEW",                     # the ONE document that changes
   "replace": [["old text", "new text"], ...],            # exact, each old found once in that document
   "new_doc": {"type", "date", "author_role", "text"},     # when doc_id is NEW (conflict: another source)
   "set_date": "YYYY-MM-DD",                              # expired: the document's new date
   "evidence": [{"quote", "concept", "value", "unit", "status"}],   # new gold evidence (violation/conflict/unsupported)
   "action": "none|patient_question|...", "note": "one line, why the expected judgment follows",
   "check_terms": ["words that must not state the same fact elsewhere in the record"]}
Expected judgment of the target criterion (common format 7):
  violation FAIL/VIOLATED none · missing UNKNOWN/MISSING · expired UNKNOWN/EXPIRED · conflict CONFLICT/CONFLICT ·
  unsupported UNKNOWN/UNSUPPORTED. Every other criterion keeps its base judgment; the trial label is recomputed.

Usage (stage2/variants): python3 build_variants.py --split dev --edits edits_dev.json --out-dir out_dev
Writes patients_variants.jsonl, gold_variants.jsonl, id_map_variants.json, build_report.txt (mentions to review).
"""
import argparse, collections, copy, csv, json, os, random, re, sys
from datetime import date
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import gold_lib as G  # noqa: E402

ROOT = os.path.join(HERE, "..", "..")
SETS = {"dev": ("patients_v2.jsonl", "stage2/runs/dev_v10", "ctgov_v2/dev/criteria.jsonl"),
        "test": ("patients_eval_v2.jsonl", "stage2/runs/test_v9", "ctgov_v2/test/criteria.jsonl")}
EXPECT = {"violation": ("FAIL", "VIOLATED"), "missing": ("UNKNOWN", "MISSING"), "expired": ("UNKNOWN", "EXPIRED"),
          "conflict": ("CONFLICT", "CONFLICT"), "unsupported": ("UNKNOWN", "UNSUPPORTED")}
ACTIONS = {"none", "patient_question", "med_record_check", "lab_check", "med_history_check", "clinician_confirmation", "new_test"}


def jl(p):
    return [json.loads(l) for l in open(os.path.join(ROOT, p), encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=SETS, required=True)
    ap.add_argument("--edits", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    pf, run, cf = SETS[a.split]
    P = {p["patient_id"]: p for p in jl(pf)}
    C = {c["criterion_id"]: c for c in jl(cf)}
    T = {t["trial_id"]: t for t in jl("ctgov_v1/trials.jsonl")}
    GD = jl(f"{run}/gold.jsonl")
    admin = collections.defaultdict(set)
    with open(os.path.join(ROOT, run, "review.csv"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("admin") or "").strip().upper() in ("Y", "YES", "1", "TRUE"):
                admin[(r["patient_id"], r["trial_id"])].add(r["criterion_id"])
    edits = json.load(open(a.edits, encoding="utf-8"))

    taken = set()
    for f in ("patients_v2.jsonl", "patients_eval_v2.jsonl"):
        taken |= {p["patient_id"] for p in jl(f)}
    import glob   # ids already given to variants of the other split
    for f in glob.glob(os.path.join(HERE, "out_*", "id_map_variants.json")):
        if os.path.abspath(os.path.dirname(f)) != os.path.abspath(a.out_dir):
            taken |= set(json.load(open(f)))
    rnd = random.Random(a.seed)

    def new_id():
        while True:
            x = f"SYN-{rnd.randint(1000, 9999)}"
            if x not in taken:
                taken.add(x)
                return x

    errors, report, out_p, out_g, idmap = [], [], [], [], {}
    for k, e in enumerate(edits):
        tag = f"[{k}] {e['base']} {e['variant']} {e['criterion_id']}"
        if e.get("skip"):          # dropped after checking; still use up its id so later ids do not move
            new_id()
            report.append(f"{tag} SKIPPED: {e['skip']}")
            continue
        try:
            base = P[e["base"]]
            st, rs = EXPECT[e["variant"]]
            act = e.get("action") or "none"
            assert act in ACTIONS, f"bad action {act}"
            if e["variant"] == "violation":
                assert act == "none", "violation action must be none"
            if e["variant"] == "conflict":
                assert act == "clinician_confirmation", "conflict action must be clinician_confirmation"
            pid = new_id()
            pre = e["base"]
            docs = copy.deepcopy(base["documents"])
            # ---- edit exactly one document
            if e["doc_id"] == "NEW":
                nd = e["new_doc"]
                n = max(int(d["doc_id"].rsplit("-D", 1)[1]) for d in docs) + 1
                edoc = {"doc_id": f"{pre}-D{n:02d}", "type": nd["type"], "date": nd["date"], "author_role": nd["author_role"],
                        "text": nd["text"]}
                docs.append(edoc)
                docs.sort(key=lambda d: (d["date"], d["doc_id"]))
            else:
                edoc = next(d for d in docs if d["doc_id"] == e["doc_id"])
                before = edoc["text"]
                for old, new in e.get("replace", []):
                    cnt = edoc["text"].count(old)
                    assert cnt == 1, f"old text found {cnt} times: {old[:60]!r}"
                    edoc["text"] = edoc["text"].replace(old, new)
                if e.get("set_date"):
                    edoc["date"] = e["set_date"]
                assert edoc["text"] != before or e.get("set_date"), "edit changed nothing"
            assert edoc["date"] <= base["as_of"], "document date after as_of"
            # ---- rename ids
            # doc ids follow the (date-sorted) document order, so an added document does not stand out by its number
            pos = {d["doc_id"]: f"{pid}-D{i:02d}" for i, d in enumerate(docs, 1)}
            ren = lambda s: pos.get(s, s.replace(pre + "-", pid + "-", 1))  # noqa: E731
            for d in docs:
                d["doc_id"] = ren(d["doc_id"])
            vdoc = {d["doc_id"]: d for d in docs}
            edoc_id = edoc["doc_id"]
            vp = dict(base, patient_id=pid, documents=docs)
            # ---- gold
            target_pair = None
            for g in [g for g in GD if g["patient_id"] == pre]:
                vg = copy.deepcopy(g)
                vg.update(patient_id=pid, variant=e["variant"], label_source="generated", injection=None)
                ev = {x["gold_ev_id"]: x for x in vg["gold_evidence"]}
                for x in vg["gold_evidence"]:
                    x["doc_id"] = ren(x["doc_id"])
                tc = next((c for c in vg["criteria"] if c["criterion_id"] == e["criterion_id"]), None)
                if tc is not None:
                    target_pair = vg
                    assert tc["expected_status"] == "PASS", "target is not PASS in the base gold"
                    old_ids = list(tc["supporting_evidence"])
                    nxt = max([int(i[1:]) for i in ev] + [0]) + 1
                    new_ids = []
                    for q in e.get("evidence", []):
                        gid = f"G{nxt:02d}"; nxt += 1
                        ev[gid] = {"gold_ev_id": gid, "concept": q.get("concept"), "value": q.get("value"), "unit": q.get("unit"),
                                   "observed_date": None, "doc_id": ren(q["doc_id"]) if q.get("doc_id") else edoc_id, "span": None, "text": q["quote"],
                                   "status": q.get("status", "observed")}
                        if q.get("term"):
                            ev[gid]["term"] = q["term"]
                        new_ids.append(gid)
                    v = e["variant"]
                    if v == "violation" or v == "unsupported":
                        assert new_ids, "new evidence required"
                        sup = new_ids
                    elif v == "conflict":
                        assert new_ids, "new evidence required"
                        sup = old_ids + new_ids
                    elif v == "missing":
                        sup = []
                    else:  # expired: the remaining, now out-of-window value (or the moved one)
                        sup = new_ids or old_ids
                    tc.update(expected_status=st, reason=rs, supporting_evidence=sup, expected_action=act, review="generated")
                    vg["injection"] = {"type": st if v != "missing" else "MISSING", "variant": v, "target_criterion": e["criterion_id"],
                                       "doc_id": edoc_id, "note": e["note"]}
                vg["injection"] = vg["injection"] or {"type": None, "variant": e["variant"], "target_criterion": e["criterion_id"],
                                                      "note": "target is in another trial of this patient"}
                # drop evidence no criterion cites; relocate evidence in the edited document
                used = {i for c in vg["criteria"] for i in c["supporting_evidence"] + c.get("decoy_evidence", [])}
                keep = []
                for gid, x in sorted(ev.items()):
                    if gid not in used:
                        continue
                    if x["doc_id"] == edoc_id or x["span"] is None:
                        sp = G.locate(vdoc[x["doc_id"]]["text"], x["text"])
                        assert sp, f"{gid} quote not found after edit: {x['text'][:60]!r}"
                        x["span"] = list(sp)
                        x["text"] = vdoc[x["doc_id"]]["text"][sp[0]:sp[1]]
                        if e.get("set_date") and x.get("observed_date"):
                            x["observed_date"] = e["set_date"]
                    keep.append(x)
                vg["gold_evidence"] = keep
                vg["trial_label"] = G.trial_label(vg["criteria"], G.structured_check(vp, T[vg["trial_id"]]),
                                                  frozenset(admin[(pre, g["trial_id"])]))
                out_g.append(vg)
            assert target_pair is not None, "target criterion not in this patient's gold"
            # removed evidence must not be cited by another criterion
            # ---- report: other mentions of the fact
            hits = []
            for term in e.get("check_terms", []):
                rx = re.compile(re.escape(term), re.I)
                for d in docs:
                    if d["doc_id"] == edoc_id:
                        continue
                    for m in rx.finditer(d["text"]):
                        hits.append(f"    {d['doc_id']} {d['date']}: ...{d['text'][max(0, m.start() - 60):m.end() + 60]}...".replace("\n", " / "))
                if rx.search(base.get("summary") or ""):
                    hits.append(f"    SUMMARY: {base['summary']}")
            base_lab = next(g["trial_label"] for g in GD if g["patient_id"] == pre and g["trial_id"] == target_pair["trial_id"])
            report.append(f"{tag} -> {pid}  {st}/{rs} {act}; trial {target_pair['trial_id']} {base_lab} -> {target_pair['trial_label']}"
                          + (f"\n  other mentions of {e.get('check_terms')}:\n" + "\n".join(hits) if hits else ""))
            out_p.append(vp)
            idmap[pid] = {"base_patient_id": pre, "variant": e["variant"], "target_criterion": e["criterion_id"]}
        except (AssertionError, KeyError, StopIteration) as ex:
            errors.append(f"{tag}: {type(ex).__name__} {ex}")

    os.makedirs(a.out_dir, exist_ok=True)
    w = lambda name, rows: open(os.path.join(a.out_dir, name), "w", encoding="utf-8").writelines(  # noqa: E731
        json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    w("patients_variants.jsonl", out_p)
    w("gold_variants.jsonl", out_g)
    json.dump(idmap, open(os.path.join(a.out_dir, "id_map_variants.json"), "w"), indent=1)
    open(os.path.join(a.out_dir, "build_report.txt"), "w", encoding="utf-8").write("\n".join(report + ["", "ERRORS:"] + errors) + "\n")
    print(f"{len(out_p)} variant patients, {len(out_g)} pairs -> {a.out_dir}; {len(errors)} errors")
    print(collections.Counter(idmap[x]["variant"] for x in idmap))
    for x in errors:
        print("ERROR", x)


if __name__ == "__main__":
    main()
