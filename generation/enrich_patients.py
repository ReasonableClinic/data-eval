#!/usr/bin/env python3
"""Stage 1.5: add a comprehensive H&P (clinic_note) and a recent routine lab panel (lab_result) to each patient.

The new documents are appended after the existing ones; existing documents are not changed. They are written
from the patient's own specification and record only (no trial criteria), so the data stays trial-independent.

Usage (stage1_patients folder):
  python3 enrich_patients.py --patients patients.jsonl --specs specs.json --id-map id_map.json \
      --out patients_v2.jsonl --provider anthropic --model claude-sonnet-5-5
  python3 validate.py patients_v2.jsonl
Resumable: patients already in --out are skipped. Log: enrich_log.jsonl.
"""
import argparse, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "stage2"))
import gold_lib as G  # noqa: E402  (LLM providers)
from validate import check  # noqa: E402

PROMPT = open(os.path.join(HERE, "prompt_enrich_patient.md"), encoding="utf-8").read()
BANNED = [r"\beligib", r"\binclusion\b", r"\bexclusion\b", r"\bcriteria\b", r"\btrials?\b",
          r"prior to enrollment", r"at screening"]   # word boundaries: "atrial" is fine


def spec_text(s):
    lines = [f"- sex: {s['sex']}",
             f"- age: {s['age_months']} months" if "age_months" in s else f"- age: {s.get('age')} years",
             f"- main condition: {s['condition']}"]
    if s.get("history"):
        lines.append(f"- relevant history: {', '.join(s['history'])}")
    if s.get("meds"):
        lines.append(f"- medications (current or past): {', '.join(s['meds'])}")
    if s.get("notes"):
        lines.append(f"- notes: {s['notes']}")
    return "\n".join(lines)


def record_text(p):
    out = [f"summary: {p['summary']}"]
    for d in p["documents"]:
        out.append(f"--- {d['date']} | {d['type']} | {d['author_role']}\n{d['text']}")
    return "\n".join(out)


def enrich(a, p, spec):
    last = max(d["date"] for d in p["documents"])
    prompt = PROMPT.format(spec=spec_text(spec), record=record_text(p), as_of=p["as_of"], first_date=last)
    errs = []
    for attempt in range(1, a.retries + 1):
        try:
            text, usage = G.call_llm(a.provider, a.model, prompt, a.temperature, max_tokens=8000)
            docs = G.parse_json(text)["documents"]
        except Exception as e:
            if type(e).__name__ in G.FATAL_ERRORS:
                raise
            errs = [f"{type(e).__name__}: {str(e)[:150]}"]
            continue
        errs = []
        if len(docs) != 2 or [d.get("type") for d in docs] != ["clinic_note", "lab_result"]:
            errs.append("need exactly two documents: clinic_note then lab_result")
        for d in docs:
            if not (last <= d.get("date", "") <= p["as_of"]):
                errs.append(f"date {d.get('date')} must be between {last} and {p['as_of']}")
            low = d.get("text", "").lower()
            errs += [f"banned word '{w}'" for w in BANNED if re.search(w, low)]
        if not errs:
            docs = sorted(docs, key=lambda d: d["date"])
            new = dict(p, documents=p["documents"] + [
                {"doc_id": f"{p['patient_id']}-D{len(p['documents']) + i + 1:02d}", "type": d["type"], "date": d["date"],
                 "author_role": d["author_role"], "text": d["text"].strip()} for i, d in enumerate(docs)])
            v_err, v_warn = [], []
            check(new, v_err, v_warn)
            if not v_err:
                return new, attempt, v_warn, usage
            errs = v_err
        prompt += "\n\nYour previous answer had these problems, fix them:\n" + "\n".join(errs[:20])
    return None, a.retries, errs, {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients", required=True)
    ap.add_argument("--specs", required=True)
    ap.add_argument("--id-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", help="comma-separated base_ids")
    a = ap.parse_args()
    G.preflight(a.provider)

    specs = {s["base_id"]: s for s in json.load(open(a.specs))["patients"]}
    id_map = json.load(open(a.id_map))
    patients = G.load_jsonl(a.patients)
    done = {p["patient_id"] for p in G.load_jsonl(a.out)} if os.path.exists(a.out) else set()
    only = set(a.only.split(",")) if a.only else None
    todo = [p for p in patients if p["patient_id"] not in done and id_map.get(p["patient_id"]) in specs
            and (only is None or id_map[p["patient_id"]] in only)]
    print(f"{len(todo)} patients to enrich")
    log_path = os.path.join(os.path.dirname(os.path.abspath(a.out)), "enrich_log.jsonl")
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(enrich, a, p, specs[id_map[p["patient_id"]]]): p for p in todo}
        for fut in as_completed(futs):
            p = futs[fut]
            new, attempts, notes, usage = fut.result()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"patient_id": p["patient_id"], "ok": new is not None, "attempts": attempts,
                                    "notes": notes, "model": a.model, "usage": usage,
                                    "created": date.today().isoformat()}, ensure_ascii=False) + "\n")
            if new is None:
                print(f"FAIL {p['patient_id']}: {notes[:2]}")
                continue
            with open(a.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(new, ensure_ascii=False) + "\n")
            print(f"OK   {p['patient_id']} ({id_map[p['patient_id']]}): +2 docs, {len(notes)} warnings")
    # keep the original patient order in the output file
    order = {p["patient_id"]: i for i, p in enumerate(patients)}
    rows = sorted(G.load_jsonl(a.out), key=lambda p: order.get(p["patient_id"], 1e9))
    G.write_jsonl(a.out, rows)
    print(f"{len(rows)} patients in {a.out}")


if __name__ == "__main__":
    main()
