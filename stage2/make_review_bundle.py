#!/usr/bin/env python3
"""Build review_bundle.json for the web review screen from a labeling run.

Reads review.csv (made by label_gold.py), the patients and the trials, and adds Korean plain-language
explanations of each criterion and of both LLM rationales (translated once, cached in ko_cache.json).

Usage (stage2 folder):
  python3 make_review_bundle.py --run runs/dev_v3 --patients ../patients_v2.jsonl --trials ../ctgov_v1/trials.jsonl \
      --provider openrouter --model openai/gpt-oss-120b
  python3 make_review_bundle.py --run runs/dev_v3 ... --no-translate     # no API calls (uses cached Korean only)
If <run>/adjudication.jsonl exists (adjudicate.py), the adjudicator's opinion is added to each criterion.
Output: <run>/review_bundle.json -> open it in the review page; export review.csv from there into <run>/,
then: python3 apply_review.py --draft <run>/gold_draft.jsonl --review <run>/review.csv ...
"""
import argparse, csv, hashlib, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_lib as G  # noqa: E402

PROMPT = """Translate each item into natural Korean for a Korean data reviewer who is not a physician.
Rules:
- Keep the meaning exact. Do not add or drop conditions, numbers, units, time windows or negations.
- Write medical terms in Korean with the English term in parentheses the first time, e.g. "절대호중구수(ANC)", "좌심실 박출률(LVEF)".
- Spell out abbreviations once (e.g. "ECOG 수행 상태 0-1", "HbA1c(당화혈색소)").
- Keep drug names, gene names and trial codes in English.
- One or two short sentences per item. No extra commentary.

Items (id | text):
{items}

Return only JSON: {{"items": [{{"id": "...", "ko": "..."}}]}}"""


def key(text):
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


def translate(a, texts, cache_path):
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    todo = {key(t): t for t in texts if t and t.strip() and key(t) not in cache}
    items = list(todo.items())
    batches = [items[i:i + a.batch] for i in range(0, len(items), a.batch)]
    print(f"{len(texts)} texts, {len(todo)} new to translate in {len(batches)} batches")

    def run(batch):
        body = "\n".join(f"{k} | {t[:600].replace(chr(10), ' ')}" for k, t in batch)
        for _ in range(3):
            try:
                out, _usage = G.call_llm(a.provider, a.model, PROMPT.format(items=body), 0.0, max_tokens=6000 + 150 * len(batch))
                got = {x["id"]: x["ko"] for x in G.parse_json(out).get("items", []) if isinstance(x, dict) and "id" in x}
                if got:
                    return got
            except Exception as e:  # noqa: BLE001
                if type(e).__name__ in G.FATAL_ERRORS:
                    raise
        return {}

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for n, fut in enumerate(as_completed([ex.submit(run, b) for b in batches]), 1):
            cache.update({k: v for k, v in fut.result().items() if k in todo})
            if n % 10 == 0 or n == len(batches):
                print(f"  {n}/{len(batches)} batches")
                json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
    missing = sum(1 for k in todo if k not in cache)
    if missing:
        print(f"  {missing} texts not translated (run again to retry; English is shown for them)")
    return cache


def adj_fields(x):
    if not x:
        return {}
    ev = " | ".join(f"{e.get('doc_id')}: {e.get('quote')}" for e in x.get("evidence") or [] if isinstance(e, dict))
    return {"adj_status": x.get("status") or "", "adj_reason": x.get("reason") or "", "adj_action": x.get("action") or "",
            "adj_evidence": ev, "adj_explain_ko": x.get("explain_ko") or "", "adj_confidence": x.get("confidence") or "",
            "adj_needs_clinician": "Y" if x.get("needs_clinician") else "", "adj_which": x.get("which") or "",
            "adj_source": x.get("source") or ""}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="folder with review.csv from label_gold.py")
    ap.add_argument("--patients", nargs="+", required=True)
    ap.add_argument("--trials", required=True)
    ap.add_argument("--provider", choices=["anthropic", "openai", "openrouter"])
    ap.add_argument("--model")
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(os.path.join(a.run, "review.csv"), encoding="utf-8-sig")))
    patients = {p["patient_id"]: p for p in G.load_jsonl(a.patients)}
    trials = {t["trial_id"]: t for t in G.load_jsonl(a.trials)}

    cache_path = os.path.join(HERE, "ko_cache.json")
    ko = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    adj_path = os.path.join(a.run, "adjudication.jsonl")
    adj = {}
    if os.path.exists(adj_path):
        for x in G.load_jsonl([adj_path]):
            if x.get("ok"):
                adj[(x["patient_id"], x["trial_id"], x["criterion_id"])] = x   # later lines win
        print(f"adjudication: {len(adj)} criteria from {adj_path}")
    if not a.no_translate:
        if not (a.provider and a.model):
            ap.error("--provider and --model are required unless --no-translate")
        G.preflight(a.provider)
        texts = set()
        for r in rows:
            texts.update([r["original_text"], r["llm_rationale"], r["llm2_rationale"]])
        for tid in {r["trial_id"] for r in rows}:
            texts.add(trials.get(tid, {}).get("title", ""))
        ko = translate(a, sorted(t for t in texts if t), cache_path)

    def k(t):
        return ko.get(key(t), "") if t else ""

    pairs = {}
    for r in rows:
        pk = f"{r['patient_id']}|{r['trial_id']}"
        if pk not in pairs:
            t = trials.get(r["trial_id"], {})
            pairs[pk] = {"key": pk, "patient_id": r["patient_id"], "base_id": r["base_id"], "trial_id": r["trial_id"],
                         "trial_title": r["trial_title"], "trial_title_ko": k(r["trial_title"]),
                         "trial_label_llm": r["trial_label_llm"], "trial_label_llm2": r.get("trial_label_llm2", ""),
                         "cohort_assignment": r["cohort_assignment"],
                         "trial_summary": (t.get("brief_summary") or "")[:1500], "rows": []}
        pairs[pk]["rows"].append({c: r.get(c, "") for c in (
            "criterion_id", "type", "admin", "cohort", "check", "original_text",
            "llm_status", "llm_reason", "llm_action", "llm_evidence", "llm_rationale",
            "llm2_status", "llm2_reason", "llm2_evidence", "llm2_rationale")}
            | {"text_ko": k(r["original_text"]), "rationale_ko": k(r["llm_rationale"]), "rationale2_ko": k(r["llm2_rationale"])}
            | adj_fields(adj.get((r["patient_id"], r["trial_id"], r["criterion_id"]))))
    used = {p["patient_id"] for p in pairs.values()}
    bundle = {"version": 1, "run": os.path.basename(os.path.abspath(a.run)),
              "columns": list(rows[0].keys()) if rows else [],
              "patients": {pid: {"patient_id": pid, "as_of": patients[pid]["as_of"], "summary": patients[pid]["summary"],
                                 "documents": patients[pid]["documents"]} for pid in used if pid in patients},
              "pairs": list(pairs.values())}
    out = os.path.join(a.run, "review_bundle.json")
    json.dump(bundle, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    n_rows = sum(len(p["rows"]) for p in bundle["pairs"])
    n_ko = sum(1 for p in bundle["pairs"] for x in p["rows"] if x["text_ko"])
    n_adj = sum(1 for p in bundle["pairs"] for x in p["rows"] if x.get("adj_status"))
    print(f"{len(bundle['pairs'])} pairs, {n_rows} criteria ({n_ko} with Korean, {n_adj} with adjudicator opinion)"
          f" -> {out} ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
