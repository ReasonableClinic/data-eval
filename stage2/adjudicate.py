#!/usr/bin/env python3
"""Third opinion ("adjudicator") for the criteria a reviewer has to look at.

For every patient x trial pair it sends ONE request with the patient record, the trial, and the flagged criteria
(rows of review.csv with a CHECK flag, plus every row of pairs whose trial labels differ between the two runs,
plus FAIL rows with --include-fail). The model returns, per criterion, a final judgment, evidence quotes and a
short Korean explanation written for a non-clinician reviewer. Results go to <run>/adjudication.jsonl and are
shown in the review page by make_review_bundle.py.

Usage (stage2 folder):
  python3 adjudicate.py --run runs/test_v3 --patients ../patients_eval_v2.jsonl --trials ../ctgov_v1/trials.jsonl \
      --provider anthropic --model claude-sonnet-5-5
Resumable: criteria already adjudicated in adjudication.jsonl are skipped; failed ones are retried.
"""
import argparse, csv, json, os, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_lib as G  # noqa: E402
from label_gold import patient_text, trial_text  # noqa: E402

PROMPT = """You are the adjudicator for a clinical-trial matching gold standard. Two earlier judges labeled each
criterion below for this patient; they disagreed or something was flagged. Decide the correct label using ONLY the
patient's documents, and explain it in Korean to a reviewer who is not a clinician.

## Judgment date (as_of)
{as_of}

## Patient
{patient}

## Trial
{trial}

## Criteria to adjudicate
{items}

## Labeling rules (same as the judges)
- Status says whether this criterion allows enrollment (also for exclusion criteria): PASS (met / excluding condition
  explicitly absent or impossible for this patient), FAIL (not met / excluding condition present), UNKNOWN (record does
  not settle it), CONFLICT (documents contradict each other).
- Reason: PASS->VALID, FAIL->VIOLATED, CONFLICT->CONFLICT, UNKNOWN->MISSING (nothing in record) | EXPIRED (older than
  the time window; imaging >90 days or labs >30 days count as too old for "current state" criteria) | UNSUPPORTED
  (something related is written but does not prove it).
- Do not assume absent diseases: an exclusion condition never mentioned is UNKNOWN/MISSING. Plans or options
  "discussed" are not treatments received. Judgment words ("clinically significant") -> UNKNOWN/UNSUPPORTED with
  clinician_confirmation unless the record states the condition itself.
- Suspected, possible or "features of" a diagnosis is not a confirmed diagnosis -> UNKNOWN/UNSUPPORTED for a criterion
  that requires it. Do not infer events or needs the record does not state (e.g. a future ICU need).
- A line that is only one option of a split list of alternatives (e.g. "Hormone receptor status not specified") is
  not failed because the patient matches another option; PASS if a neighbouring line shows an allowed option matches.
- A criterion for a different cohort than the patient's -> status "N/A".
- Action for UNKNOWN/CONFLICT: patient_question | med_record_check | lab_check | med_history_check |
  clinician_confirmation | new_test. PASS/FAIL/N/A -> none.
- Evidence: exact quotes copied character for character from one document (short), with doc_id. Needed for PASS,
  FAIL, CONFLICT, and UNKNOWN with EXPIRED/UNSUPPORTED.

## Korean explanation (explain_ko)
2-3 short sentences in plain Korean: what the criterion asks, what the record says (with the date), and the
conclusion. Translate medical terms the first time with the English in parentheses. Say which earlier judge was
right ("1차가 맞음", "2차가 맞음", or "둘 다 틀림").
confidence: "high" if the record states it clearly, "medium" if it needs some clinical inference, "low" if a
clinician should check. needs_clinician: true when a non-clinician should not decide it alone.

Return only JSON:
{{"items": [{{"criterion_id": "...", "status": "PASS|FAIL|UNKNOWN|CONFLICT|N/A", "reason": "...", "action": "...",
  "evidence": [{{"doc_id": "...", "quote": "..."}}], "which": "1|2|neither|both", "explain_ko": "...",
  "confidence": "high|medium|low", "needs_clinician": false}}]}}"""


def item_text(r):
    def ev(s):
        return s or "-"
    return (f"- {r['criterion_id']} | {r['type']} | cohort: {r['cohort'] or '-'}\n  text: {r['original_text']}\n"
            f"  judge 1: {r['llm_status']}/{r['llm_reason']} action={r['llm_action']} evidence={ev(r['llm_evidence'])} "
            f"rationale={r['llm_rationale']}\n"
            f"  judge 2: {r['llm2_status']}/{r['llm2_reason']} evidence={ev(r['llm2_evidence'])} rationale={r['llm2_rationale']}")


def check_item(x, patient):
    st = x.get("status")
    if st == "N/A":
        return []
    probs = G.check_criterion({"criterion_id": x.get("criterion_id"), "expected_status": st,
                               "reason": x.get("reason"), "expected_action": x.get("action")})
    if (st, x.get("reason")) in G.NEEDS_EVIDENCE and not x.get("evidence"):
        probs.append(f"{x.get('criterion_id')}: needs evidence")
    _, _, q = G.build_gold_evidence([{"criterion_id": x.get("criterion_id"), "evidence": x.get("evidence")}], patient)
    return probs + q


def adjudicate_pair(a, key, rows, patient, trial):
    want = {r["criterion_id"] for r in rows}
    prompt = PROMPT.format(as_of=patient["as_of"], patient=patient_text(patient), trial=trial_text(trial),
                           items="\n".join(item_text(r) for r in rows))
    got, problems = {}, {}
    for attempt in range(1, 4):
        todo = [r for r in rows if r["criterion_id"] not in got]
        if not todo:
            break
        p = prompt if attempt == 1 else PROMPT.format(
            as_of=patient["as_of"], patient=patient_text(patient), trial=trial_text(trial),
            items="\n".join(item_text(r) for r in todo)) + "\n\nFix these problems from your previous answer:\n" + \
            "\n".join(f"- {c}: {'; '.join(v)[:200]}" for c, v in problems.items())
        try:
            text, _ = G.call_llm(a.provider, a.model, p, 0.0, max_tokens=4000 + 600 * len(todo))
            items = G.parse_json(text).get("items", [])
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ in G.FATAL_ERRORS:
                raise
            continue
        problems = {}
        for x in items if isinstance(items, list) else []:
            if not isinstance(x, dict) or x.get("criterion_id") not in want or x["criterion_id"] in got:
                continue
            pr = check_item(x, patient)
            if pr:
                problems[x["criterion_id"]] = pr
            else:
                got[x["criterion_id"]] = x
    pid, tid = key
    out = []
    for r in rows:
        x = got.get(r["criterion_id"])
        out.append({"patient_id": pid, "trial_id": tid, "criterion_id": r["criterion_id"],
                    "status": x and x["status"], "reason": x and x.get("reason"), "action": x and x.get("action"),
                    "evidence": (x and x.get("evidence")) or [], "which": x and x.get("which"),
                    "explain_ko": (x and x.get("explain_ko")) or "", "confidence": (x and x.get("confidence")) or "",
                    "needs_clinician": bool(x and x.get("needs_clinician")) if x else True,
                    "ok": x is not None, "source": f"{a.provider}:{a.model}", "created": date.today().isoformat()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--patients", nargs="+", required=True)
    ap.add_argument("--trials", required=True)
    ap.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--include-fail", action="store_true", help="also adjudicate rows where judge 1 said FAIL")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    G.preflight(a.provider)

    rows = list(csv.DictReader(open(os.path.join(a.run, "review.csv"), encoding="utf-8-sig")))
    patients = {p["patient_id"]: p for p in G.load_jsonl(a.patients)}
    trials = {t["trial_id"]: t for t in G.load_jsonl(a.trials)}
    out_path = os.path.join(a.run, "adjudication.jsonl")
    done_ok = {}   # pair -> criteria already adjudicated successfully (failed ones are retried on the next run)
    if os.path.exists(out_path):
        for x in G.load_jsonl([out_path]):
            if x.get("ok"):
                done_ok.setdefault((x["patient_id"], x["trial_id"]), set()).add(x["criterion_id"])

    by_pair = {}
    for r in rows:
        by_pair.setdefault((r["patient_id"], r["trial_id"]), []).append(r)
    jobs = []
    for k, rs in by_pair.items():
        if k[0] not in patients:
            continue
        label_diff = rs[0].get("trial_label_llm2") and rs[0]["trial_label_llm"] != rs[0]["trial_label_llm2"]
        pick = rs if label_diff else [r for r in rs if r["check"] or (a.include_fail and r["llm_status"] == "FAIL")]
        pick = [r for r in pick if r["criterion_id"] not in done_ok.get(k, ())]
        if pick:
            jobs.append((k, pick))
    n = sum(len(p) for _, p in jobs)
    print(f"{len(jobs)} pairs, {n} criteria to adjudicate with {a.model}")
    ok = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(adjudicate_pair, a, k, pick, patients[k[0]], trials[k[1]]): k for k, pick in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            k = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # noqa: BLE001
                if type(e).__name__ in G.FATAL_ERRORS:
                    sys.exit(f"STOP: {type(e).__name__}: {e}")
                print(f"FAIL {k[0]} x {k[1]}: {type(e).__name__}: {str(e)[:120]}")
                continue
            ok += sum(x["ok"] for x in res)
            with open(out_path, "a", encoding="utf-8") as f:
                for x in res:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(jobs)}] {k[0]} x {k[1]}: {sum(x['ok'] for x in res)}/{len(res)} adjudicated")
    print(f"done: {ok}/{n} criteria -> {out_path}")


if __name__ == "__main__":
    main()
