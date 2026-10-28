#!/usr/bin/env python3
"""Criterion-level check of our LLM labeler against TrialGPT expert annotations (common format 10장, proposal 6).

Data: Hugging Face `ncbi/TrialGPT-Criterion-Annotations` (public domain): 1,015 patient-criterion rows,
53 patients, 105 patient-trial pairs, judged by physicians. Labels:
  inclusion: included / not included / not enough information / not applicable
  exclusion: excluded / not excluded / not enough information / not applicable

Steps (run in this folder, from your own terminal: the download needs internet):
  python3 trialgpt_eval.py fetch                  -> data/criterion_annotations.jsonl
  python3 trialgpt_eval.py build                  -> data/patients.jsonl, trials.jsonl, criteria.jsonl,
                                                     trial_candidates.jsonl, id_map.json, expert.jsonl
  python3 ../../label_gold.py --trials data/trials.jsonl --criteria data/criteria.jsonl --patients data/patients.jsonl --id-map data/id_map.json --candidates data/trial_candidates.jsonl --provider openrouter --model openai/gpt-oss-120b --out runs/tg_v1/gold_draft.jsonl
  python3 trialgpt_eval.py compare --run runs/tg_v1

Mapping of our status to TrialGPT labels (criterion type decides the wording):
  PASS -> included / not excluded,  FAIL -> not included / excluded,
  UNKNOWN or CONFLICT -> not enough information,  applies=false (other cohort) -> not applicable.
`compare` also reports a variant where an exclusion criterion that is UNKNOWN/MISSING (never mentioned) counts as
"not excluded", because TrialGPT annotators often read silence that way while our gold rule keeps it UNKNOWN.
"""
import argparse, collections, json, os, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DATASET = "ncbi/TrialGPT-Criterion-Annotations"
ROWS = "https://datasets-server.huggingface.co/rows"
AS_OF = "2021-04-27"     # TrialGPT notes come from TREC-style topics without dates; any fixed date works


def jl(p):
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def wjl(p, rows):
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- fetch

def fetch(a):
    os.makedirs(DATA, exist_ok=True)
    out, total, offset = [], None, 0
    while total is None or offset < total:
        q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "train",
                                    "offset": offset, "length": 100})
        req = urllib.request.Request(f"{ROWS}?{q}", headers={"accept": "application/json", "user-agent": "trialgpt-eval/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.loads(r.read().decode("utf-8"))
        total = page["num_rows_total"]
        rows = [x["row"] for x in page["rows"]]
        if not rows:
            break
        out += rows
        offset += len(rows)
        print(f"  {offset}/{total}")
    path = os.path.join(DATA, "criterion_annotations.jsonl")
    wjl(path, out)
    print(f"{len(out)} rows -> {path}")


# ---------------------------------------------------------------- build

def build(a):
    rows = jl(os.path.join(DATA, "criterion_annotations.jsonl"))
    rows = [r for r in rows if (r.get("criterion_text") or "").strip()]
    print(f"{len(rows)} rows with criterion text; fields: {sorted(rows[0])}")
    pid = lambda r: f"TG-{r['patient_id']}"  # noqa: E731

    # one ID per (trial, type, text), numbered in annotation order so every patient sees the same IDs
    ids, counters = {}, collections.Counter()
    for r in sorted(rows, key=lambda r: r["annotation_id"]):
        k = (r["trial_id"], r["criterion_type"], r["criterion_text"].strip())
        if k not in ids:
            letter = "I" if r["criterion_type"] == "inclusion" else "E"
            counters[(r["trial_id"], letter)] += 1
            ids[k] = f"{r['trial_id']}-{letter}{counters[(r['trial_id'], letter)]:02d}"

    patients, trials, criteria, cands, expert = {}, {}, {}, collections.defaultdict(set), []
    for r in rows:
        p = pid(r)
        patients.setdefault(p, {"patient_id": p, "as_of": AS_OF, "summary": r["note"][:300],
                                "documents": [{"doc_id": f"{p}-D01", "type": "clinic_note", "date": AS_OF,
                                               "author_role": "physician", "text": r["note"]}]})
        trials.setdefault(r["trial_id"], {"trial_id": r["trial_id"], "title": r["trial_title"], "phases": [],
                                          "min_age": None, "max_age": None, "sex": "ALL", "arms": [],
                                          "brief_summary": "", "criteria_complete": False})
        cid = ids[(r["trial_id"], r["criterion_type"], r["criterion_text"].strip())]
        criteria[cid] = {"trial_id": r["trial_id"], "criterion_id": cid, "type": r["criterion_type"],
                         "original_text": r["criterion_text"].strip(), "cohort": None, "parse_status": "split_only"}
        cands[p].add(r["trial_id"])
        expert.append({"patient_id": p, "trial_id": r["trial_id"], "criterion_id": cid, "type": r["criterion_type"],
                       "expert": r["expert_eligibility"], "gpt4": r.get("gpt4_eligibility"),
                       "training": r.get("training"), "annotation_id": r["annotation_id"]})
    crit_rows = sorted(criteria.values(), key=lambda c: (c["trial_id"], c["criterion_id"]))
    wjl(os.path.join(DATA, "patients.jsonl"), list(patients.values()))
    wjl(os.path.join(DATA, "trials.jsonl"), list(trials.values()))
    wjl(os.path.join(DATA, "criteria.jsonl"), crit_rows)
    wjl(os.path.join(DATA, "trial_candidates.jsonl"),
        [{"base_id": p, "split": "trialgpt", "trial_ids": sorted(t)} for p, t in sorted(cands.items())])
    json.dump({p: p for p in patients}, open(os.path.join(DATA, "id_map.json"), "w"), indent=1)
    wjl(os.path.join(DATA, "expert.jsonl"), expert)
    print(f"{len(patients)} patients, {len(trials)} trials, {len(crit_rows)} criteria, "
          f"{sum(len(t) for t in cands.values())} pairs, {len(expert)} expert labels -> {DATA}")
    print("expert labels:", dict(collections.Counter(e["expert"] for e in expert)))


# ---------------------------------------------------------------- compare

def to_label(ctype, status, reason, silence_as_absent=False):
    inc = ctype == "inclusion"
    if status is None:
        return "not applicable"
    if status == "PASS":
        return "included" if inc else "not excluded"
    if status == "FAIL":
        return "not included" if inc else "excluded"
    if silence_as_absent and not inc and status == "UNKNOWN" and reason == "MISSING":
        return "not excluded"
    return "not enough information"


def score(pairs):
    n = len(pairs)
    return (sum(a == b for a, b in pairs), n)


def compare(a):
    expert = jl(os.path.join(DATA, "expert.jsonl"))
    out = {}
    for name, f, nf in (("run1", "gold_draft.jsonl", "gold_draft_notes.jsonl"),
                        ("run2", "gold_draft.run2.jsonl", "gold_draft_notes.run2.jsonl")):
        gp = os.path.join(a.run, f)
        if not os.path.exists(gp):
            continue
        judged = {}
        for g in jl(gp):
            for c in g["criteria"]:
                judged[(g["patient_id"], c["criterion_id"])] = (c["expected_status"], c.get("reason"))
        na = set()
        if os.path.exists(os.path.join(a.run, nf)):
            for n in jl(os.path.join(a.run, nf)):
                for cid in n.get("not_applicable") or []:
                    na.add((n["patient_id"], cid))
        res = {}
        for variant, silence in (("strict", False), ("silence_as_not_excluded", True)):
            pairs, by_type, conf, missing = [], collections.defaultdict(list), collections.Counter(), 0
            for e in expert:
                k = (e["patient_id"], e["criterion_id"])
                if k in judged:
                    st, rs = judged[k]
                    ours = to_label(e["type"], st, rs, silence)
                elif k in na:
                    ours = "not applicable"
                else:
                    missing += 1
                    continue
                pairs.append((ours, e["expert"]))
                by_type[e["type"]].append((ours, e["expert"]))
                conf[(e["expert"], ours)] += 1
            ok, n = score(pairs)
            res[variant] = {
                "criteria_scored": n, "missing_from_run": missing, "accuracy": round(ok / n, 3) if n else None,
                "inclusion": round(score(by_type["inclusion"])[0] / max(1, len(by_type["inclusion"])), 3),
                "exclusion": round(score(by_type["exclusion"])[0] / max(1, len(by_type["exclusion"])), 3),
                "confusion_expert_vs_ours": {f"{x} -> {y}": c for (x, y), c in sorted(conf.items())},
            }
        out[name] = res
    gpt = [(e["gpt4"], e["expert"]) for e in expert if e.get("gpt4")]
    out["reference"] = {"gpt4_in_dataset_accuracy": round(score(gpt)[0] / len(gpt), 3) if gpt else None,
                        "trialgpt_paper": "GPT-4 0.873 (inclusion 0.899, exclusion 0.859); experts 0.887-0.900"}
    json.dump(out, open(os.path.join(a.run, "trialgpt_compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for name, res in out.items():
        if name == "reference":
            print("reference:", res)
            continue
        for v, r in res.items():
            print(f"{name} {v:<24} accuracy {r['accuracy']} (inclusion {r['inclusion']}, exclusion {r['exclusion']}), "
                  f"{r['criteria_scored']} scored, {r['missing_from_run']} missing")
    print(f"details -> {os.path.join(a.run, 'trialgpt_compare.json')}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("build")
    c = sub.add_parser("compare")
    c.add_argument("--run", required=True)
    a = ap.parse_args()
    {"fetch": fetch, "build": build, "compare": compare}[a.cmd](a)


if __name__ == "__main__":
    main()
