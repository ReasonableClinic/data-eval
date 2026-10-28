#!/usr/bin/env python3
"""Assemble hand-written base records into the shared ② Patient Record format.

Outputs:
  patients.jsonl       ② Patient Record (agent input)
  topics.json          contest format {"topics":[{"num","title"}]}
  id_map.json          patient_id <-> base_id (NOT for agents; used in stage 2/3)
  generation_meta.json
"""
import json, os, random
from records_s import RECORDS_S
from records_c import RECORDS_C

HERE = os.path.dirname(os.path.abspath(__file__))
SPECS = json.load(open(os.path.join(HERE, "specs.json")))
AS_OF = SPECS["as_of"]
SEED = 20261004

def main():
    records = {**RECORDS_S, **RECORDS_C}
    base_ids = [p["base_id"] for p in SPECS["patients"]]
    assert set(base_ids) == set(records), set(base_ids) ^ set(records)
    nums = list(range(1, len(base_ids) + 1))
    random.Random(SEED).shuffle(nums)
    id_map = {b: f"SYN-{n:04d}" for b, n in zip(base_ids, nums)}

    patients = []
    for b in sorted(base_ids, key=lambda x: id_map[x]):
        pid, r = id_map[b], records[b]
        docs = sorted(r["docs"], key=lambda d: d[1])  # stable: same-date docs keep written order
        patients.append({
            "patient_id": pid, "as_of": AS_OF, "summary": r["summary"],
            "documents": [{"doc_id": f"{pid}-D{i:02d}", "type": t, "date": d, "author_role": a, "text": x}
                          for i, (t, d, a, x) in enumerate(docs, 1)],
        })

    with open(os.path.join(HERE, "patients.jsonl"), "w") as f:
        for p in patients:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    json.dump({"topics": [{"num": p["patient_id"], "title": p["summary"]} for p in patients]},
              open(os.path.join(HERE, "topics.json"), "w"), indent=2, ensure_ascii=False)
    json.dump({pid: b for b, pid in sorted(id_map.items(), key=lambda kv: kv[1])},
              open(os.path.join(HERE, "id_map.json"), "w"), indent=2)
    json.dump({
        "format_version": "0.3", "stage": 1, "created": "2026-10-04", "as_of": AS_OF, "seed": SEED,
        "method": "Hand-written by an LLM (Claude) in a working session from specs.json; no trial criteria used. "
                  "S001-S010 summaries are the contest example texts; documents are fictional expansions.",
        "data_sources": ["Healthcare Agentic AI Challenge 2026 example patients (S001-S010 summaries)"],
        "license_note": "Fully synthetic. No real patient data. Any resemblance to real persons is coincidental.",
    }, open(os.path.join(HERE, "generation_meta.json"), "w"), indent=2, ensure_ascii=False)
    print(f"{len(patients)} patients, {sum(len(p['documents']) for p in patients)} documents")

if __name__ == "__main__":
    main()
