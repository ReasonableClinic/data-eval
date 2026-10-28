#!/usr/bin/env python3
"""Fill concept / value / unit of gold_evidence in gold.jsonl (common format 6장) once ①-b and concepts.json exist.

gold_evidence items already have doc_id, span, text and observed_date (the document date). This script asks an LLM
which concept each quote is about and what value it states, using the ①-b concept of the criteria the evidence
supports as the first candidate. Answers are validated against concepts.json (known key, numeric value and a
convertible unit for labs, true/false for conditions and drugs, date not after as_of) and stored in a cache
(<run>/evidence_concepts.jsonl), so apply_review.py can rebuild gold.jsonl and this script refills it without new
LLM calls.

Order:  apply_review.py  ->  fill_gold_evidence.py --apply  ->  make_handoff.py

Usage (stage2 folder):
  python3 fill_gold_evidence.py --run runs/dev_v5 --patients ../patients_v2.jsonl --criteria ../ctgov_v2/dev/criteria.jsonl --concepts ../ctgov_v2/concepts.json --dry-run
  python3 fill_gold_evidence.py --run runs/dev_v5 --patients ../patients_v2.jsonl --criteria ../ctgov_v2/dev/criteria.jsonl --concepts ../ctgov_v2/concepts.json --provider openrouter --model openai/gpt-oss-120b
  python3 fill_gold_evidence.py ... --apply          # write into gold.jsonl (backup gold.before_fill.jsonl)
  python3 fill_gold_evidence.py ... --apply --allow-problems   # same, leaving still-failing evidence empty
Outputs: <run>/gold.filled.jsonl, <run>/fill_report.csv (one row per evidence, check the PROBLEM rows), the cache.
Values are stored in the concept's default unit (converted with alt_units); the unit written in the record is
kept in the report.
"""
import argparse, collections, csv, hashlib, json, os, shutil, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_lib as G  # noqa: E402
from check_concepts import load_concepts, unit_ok  # noqa: E402

NUMERIC_TYPES = {"lab", "vital", "measurement"}
BOOL_TYPES = {"condition", "drug", "procedure", "behavior"}
# generic ("basket") keys: the concept says what kind of fact, `term` says which one (same as ③ term)
GENERIC = {"diagnosis", "medication", "procedure", "symptom_finding", "allergy", "metastasis", "biomarker", "lab_other",
           "tumor_marker", "cancer_stage", "treatment_plan", "social_history"}
STATUSES = {"observed", "current", "past", "stopped", "planned", "declined"}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
RESULT_WORDS = ("negative", "positive", "not detected", "undetectable", "detected", "trace", "nonreactive", "reactive")
SAME_UNITS = {"x10^9/l": "10^9/l", "×10^9/l": "10^9/l", "x10^3/ul": "10^9/l", "10^3/ul": "10^9/l", "k/ul": "10^9/l",
              "x10^12/l": "10^12/l", "×10^12/l": "10^12/l"}


def parse_number(val, key):
    """Turn record-style numbers into one number: '1/7' or '23/30' (score out of max) -> 1, 23; '16/16' (two eyes)
    -> 16; '5-7' -> 6 (middle); 'III' -> 3; 'A6' (Child-Pugh class+points) -> 6. Returns None if not a number."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return val
    if not isinstance(val, str):
        return None
    v = val.strip().replace(",", "")
    try:
        return float(v)
    except ValueError:
        pass
    import re
    if v.lower() in ROMAN:
        return ROMAN[v.lower()]
    m = re.fullmatch(r"(?:class\s*)?([ivIV]+)", v)
    if m and m.group(1).lower() in ROMAN:
        return ROMAN[m.group(1).lower()]
    m = re.fullmatch(r"[ABCabc]\s*(\d+)", v)                    # Child-Pugh A6 -> 6 points
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", v)  # 1/7, 23/30, 16/16
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", v)  # 5-7 -> 6
    if m:
        return round((float(m.group(1)) + float(m.group(2))) / 2, 3)
    return None

PROMPT = """You are normalizing evidence quotes from a patient's record into structured facts.

For each quote, choose the concept it states (a key from the concept list), the value, the unit written in the
quote, and the date the fact was observed if the quote itself gives one. Rules:
- Prefer the candidate concepts listed with the quote (they come from the trial criteria this quote supports).
  Use another key from the concept list only if the quote clearly states that concept instead. If no key fits, "concept": null.
- Numeric concepts (lab, vital, measurement): "value" is the number exactly as written (no conversion), "unit" the
  unit as written (or null if none is written).
- Conditions, drugs, procedures, behaviors: "value" true if the quote says the patient has / takes / had it,
  false if the quote explicitly denies it ("No prior malignancy" -> false). "unit": null.
- Demographics: age -> number in years, sex -> "male" / "female", other -> the written value.
- "term": for the generic concepts ({generic}) the specific thing as written in the quote
  ("acute pancreatitis", "pancrelipase", "KRAS G12D"); otherwise null.
- "status": observed (measurement or finding) / current (ongoing condition, drug being taken) / past (history,
  completed, quit habit) / stopped / planned (plan, option discussed, advice) / declined. A habit the patient quit is
  value true + status past ("Ex-smoker", "quit 2020"); false means never / explicitly denied.
- When the quote gives the value in the concept's default unit as well ("FVC 1.92 L (64% predicted)" and fvc is in %),
  use that one. Qualitative results ("not detected", "trace", "negative") are written as the word.
- For a blanket denial ("NKDA", "No other cardiac ... history") value is false and term is what is denied
  ("drug allergies", "cardiac history").
- Labs without a default unit (lab_other, biomarker): value is the number or the result word as written
  ("positive", "G12D"), unit as written.
- "subject": "family" if the quote is about a relative (family history), otherwise "patient".
- "observed_date": YYYY-MM-DD only when the quote states a specific date for the fact; otherwise null (the document
  date is used). Never invent dates.

Judgment date (as_of): {as_of}

Concept list (key | type | name | default unit):
{concepts}

Quotes (gold_ev_id | document type, date | candidate concepts | text):
{items}

Return only JSON: {{"items": [{{"gold_ev_id": "...", "concept": "...", "term": null, "value": ..., "unit": ..., "status": "observed", "subject": "patient", "observed_date": null}}]}}"""


def ev_key(patient_id, ev):
    """Stable cache key: same document span and text -> same answer."""
    raw = f"{patient_id}|{ev['doc_id']}|{ev['span'][0]}|{ev['span'][1]}|{ev['text']}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def normalize(ans, concepts, as_of):
    """Validate one LLM answer. Returns (fields to write, problems, written unit)."""
    k = ans.get("concept")
    if k is None:
        return {"concept": None, "value": None, "unit": None}, ["no concept fits"], None
    c = concepts.get(k)
    if not c:
        return None, [f"unknown concept {k!r}"], None
    t, val, unit = c.get("type"), ans.get("value"), ans.get("unit")
    probs, out = [], {"concept": k}
    term = ans.get("term")
    if k in GENERIC and not (isinstance(term, str) and term.strip()) and isinstance(val, str) and val.strip() \
            and c.get("type") in BOOL_TYPES:
        term, val = val.strip(), True                            # "metformin 1000 mg bid" given as the value
    if k in GENERIC:
        if isinstance(term, str) and term.strip():
            out["term"] = term.strip()
        elif val is not False:
            probs.append(f"generic concept {k} needs a term")   # a blanket denial ("NKDA") may have no term
    st = ans.get("status")
    if st is not None:
        if st in STATUSES:
            out["status"] = st
        else:
            probs.append(f"bad status {st!r}")
    if t in NUMERIC_TYPES and isinstance(val, bool):
        val = "positive" if val else "negative"                  # serology given as true/false
    if t in NUMERIC_TYPES and k == "blood_pressure" and isinstance(val, str) and "/" in val:
        out.update(value=val.strip(), unit=c.get("unit"))        # "136/84" kept as systolic/diastolic text
        t = "_done"
    elif t in NUMERIC_TYPES and isinstance(val, str) and parse_number(val, k) is None \
            and any(w in val.lower() for w in RESULT_WORDS):
        out.update(value=val.strip(), unit=unit or c.get("unit"))  # qualitative result: "not detected", "trace"
        t = "_done"
    elif t in NUMERIC_TYPES and isinstance(val, str):
        n = parse_number(val, k)
        if n is not None:
            val = n
    if unit:
        unit = SAME_UNITS.get(unit.replace(" ", "").lower(), unit)
    if t == "_done":
        pass
    elif t in NUMERIC_TYPES and not c.get("unit"):
        # lab_other, biomarker: number or result word, unit kept as written
        if val is None or isinstance(val, bool):
            probs.append(f"value for {k} must be a number or a result word, got {val!r}")
        out.update(value=val, unit=unit)
    elif t in NUMERIC_TYPES:
        if isinstance(val, str):
            try:
                val = float(val.replace(",", ""))
            except ValueError:
                probs.append(f"value {val!r} is not a number")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            base = c.get("unit")
            if unit and base and not unit_ok({"unit": base}, unit):
                factor = next((f for u, f in (c.get("alt_units") or {}).items()
                               if u.replace(" ", "").lower() == unit.replace(" ", "").lower()), None)
                if factor is None:
                    probs.append(f"unit {unit!r} cannot be converted to {base!r} (add it to alt_units)")
                else:
                    val = round(val * factor, 6)
            out.update(value=val, unit=base)
        elif not probs:
            probs.append(f"value {val!r} is not a number")
    elif t in BOOL_TYPES:
        if not isinstance(val, bool):
            probs.append(f"value for {t} must be true/false, got {val!r}")
        out.update(value=val, unit=None)
    else:
        out.update(value=val, unit=unit or c.get("unit"))
    od = ans.get("observed_date")
    if od:
        try:
            if date.fromisoformat(od) > date.fromisoformat(as_of):
                probs.append(f"observed_date {od} is after as_of")
            else:
                out["observed_date"] = od
        except (TypeError, ValueError):
            probs.append(f"bad observed_date {od!r}")
    if ans.get("subject") == "family":
        out["subject"] = "family"
    return (None if probs else out), probs, unit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="folder with gold.jsonl")
    ap.add_argument("--patients", nargs="+", required=True)
    ap.add_argument("--criteria", required=True, help="criteria.jsonl with ①-b concept fields")
    ap.add_argument("--concepts", required=True)
    ap.add_argument("--provider", choices=["anthropic", "openai", "openrouter"])
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt and counts, call nothing")
    ap.add_argument("--cache-only", action="store_true",
                    help="no LLM calls: fill from the cache only (after apply_review rebuilt gold); new quotes stay empty")
    ap.add_argument("--apply", action="store_true", help="write the result into gold.jsonl (backup first)")
    ap.add_argument("--allow-problems", action="store_true",
                    help="with --apply: write even if some evidence still has problems (they stay empty)")
    a = ap.parse_args()

    gold_path = os.path.join(a.run, "gold.jsonl")
    cache_path = os.path.join(a.run, "evidence_concepts.jsonl")
    golds = G.load_jsonl([gold_path])
    patients = {p["patient_id"]: p for p in G.load_jsonl(a.patients)}
    concept_list = load_concepts(a.concepts)
    concepts = {c["key"]: c for c in concept_list}
    crit = {c["criterion_id"]: c for c in G.load_jsonl([a.criteria])}
    cache = {x["key"]: x for x in G.load_jsonl([cache_path])} if os.path.exists(cache_path) else {}

    # evidence that still needs an answer, grouped by pair (one LLM call per pair)
    jobs = []
    for g in golds:
        cand = collections.defaultdict(set)
        for c in g["criteria"]:
            cr = crit.get(c["criterion_id"]) or {}
            k = cr.get("concept")
            if k and cr.get("term"):
                terms = cr["term"] if isinstance(cr["term"], list) else [cr["term"]]
                k = f"{k}[{'/'.join(str(t) for t in terms)}]"
            for e in c["supporting_evidence"] + c.get("decoy_evidence", []):
                if k:
                    cand[e].add(k)
        todo = [(e, sorted(cand[e["gold_ev_id"]])) for e in g["gold_evidence"]
                if ev_key(g["patient_id"], e) not in cache]
        if todo:
            jobs.append((g, todo))
    n_ev = sum(len(g["gold_evidence"]) for g in golds)
    n_todo = sum(len(t) for _, t in jobs)
    print(f"{len(golds)} pairs, {n_ev} gold evidence, {n_ev - n_todo} cached, {n_todo} to fill in {len(jobs)} calls")

    concept_text = "\n".join(f"{c['key']} | {c.get('type') or '-'} | {c.get('name')} | {c.get('unit') or '-'}"
                             for c in concept_list)

    def prompt(g, todo):
        docs = {d["doc_id"]: d for d in patients[g["patient_id"]]["documents"]}
        items = "\n".join(f"{e['gold_ev_id']} | {docs.get(e['doc_id'], {}).get('type')}, {e.get('observed_date')} | "
                          f"{', '.join(k) or '-'} | {e['text']}" for e, k in todo)
        return PROMPT.format(as_of=g["as_of"], concepts=concept_text, items=items, generic=", ".join(sorted(GENERIC)))

    if a.dry_run:
        if jobs:
            print(prompt(*jobs[0]))
        return
    if a.cache_only:
        jobs = []
    if jobs:
        if not (a.provider and a.model):
            ap.error("--provider and --model are required (or --dry-run)")
        G.preflight(a.provider)

    def run(g, todo):
        got, last = {}, {}
        for _ in range(3):
            left = [(e, k) for e, k in todo if e["gold_ev_id"] not in got]
            if not left:
                break
            try:
                text, _u = G.call_llm(a.provider, a.model, prompt(g, left), 0.0, max_tokens=3000 + 200 * len(left))
                items = G.parse_json(text).get("items", [])
            except Exception as e:  # noqa: BLE001
                if type(e).__name__ in G.FATAL_ERRORS:
                    raise
                continue
            for ans in items if isinstance(items, list) else []:
                if not isinstance(ans, dict):
                    continue
                ev = next((e for e, _k in left if e["gold_ev_id"] == ans.get("gold_ev_id")), None)
                if ev is None:
                    continue
                fields, probs, written = normalize(ans, concepts, g["as_of"])
                last[ev["gold_ev_id"]] = (ans, probs, written)
                if fields is not None:
                    got[ev["gold_ev_id"]] = (fields, probs, written, ans)
        rows = []
        for e, k in todo:
            if e["gold_ev_id"] in got:
                fields, probs, written, ans = got[e["gold_ev_id"]]
            else:
                ans, probs, written = last.get(e["gold_ev_id"], ({}, ["no valid answer"], None))
                fields = None
            rows.append({"key": ev_key(g["patient_id"], e), "patient_id": g["patient_id"], "doc_id": e["doc_id"],
                         "text": e["text"], "candidates": k, "fields": fields, "problems": probs,
                         "written_unit": written, "raw": ans, "source": f"{a.provider}:{a.model}"})
        return rows

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(run, g, t) for g, t in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            rows = f.result()
            with open(cache_path, "a", encoding="utf-8") as fh:
                for r in rows:
                    if r["fields"] is not None:          # only valid answers are cached; problems are retried next time
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                        cache[r["key"]] = r
            for r in rows:
                if r["fields"] is None:
                    cache.setdefault("_failed", []).append(r)
            if i % 10 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)} pairs")

    failed = {r["key"]: r for r in cache.pop("_failed", [])}
    out_rows, report = [], []
    stats = collections.Counter()
    for g in golds:
        ng = json.loads(json.dumps(g))
        for e in ng["gold_evidence"]:
            k = ev_key(g["patient_id"], e)
            r = cache.get(k) or failed.get(k)
            if r and r["fields"] is not None:
                e.update(r["fields"])
                stats["filled" if r["fields"].get("concept") else "no concept fits"] += 1
            else:
                stats["problem"] += 1
            report.append([g["patient_id"], g["trial_id"], e["gold_ev_id"], e["doc_id"], e["text"],
                           ", ".join((r or {}).get("candidates") or []), e.get("concept"), e.get("term"), e.get("value"), e.get("unit"), e.get("status"),
                           (r or {}).get("written_unit") or "", "; ".join((r or {}).get("problems") or [])
                           if not (r and r["fields"] is not None) else "",
                           "PROBLEM" if not (r and r["fields"] is not None) else ""])
        out_rows.append(ng)
    G.write_jsonl(os.path.join(a.run, "gold.filled.jsonl"), out_rows)
    with open(os.path.join(a.run, "fill_report.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["patient_id", "trial_id", "gold_ev_id", "doc_id", "text", "candidates", "concept", "term", "value",
                    "unit", "status", "written_unit", "problems", "flag"])
        w.writerows(report)
    print(f"evidence: {dict(stats)} -> {os.path.join(a.run, 'gold.filled.jsonl')}, fill_report.csv")
    if a.apply:
        if stats["problem"] and not a.allow_problems:
            print(f"--apply skipped: {stats['problem']} evidence items have problems (see fill_report.csv, run again to retry)")
            sys.exit(1)
        shutil.copy(gold_path, os.path.join(a.run, "gold.before_fill.jsonl"))
        shutil.copy(os.path.join(a.run, "gold.filled.jsonl"), gold_path)
        print(f"applied -> {gold_path} (backup gold.before_fill.jsonl)")


if __name__ == "__main__":
    main()
