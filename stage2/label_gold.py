#!/usr/bin/env python3
"""Stage 2: LLM first-pass gold labels (④) for patient x trial pairs, plus a review sheet.

Inputs (common format v0.4):
  --trials      trials.jsonl      ⓪ from the CT.gov owner
  --criteria    criteria.jsonl    ①-a (①-b optional)
  --patients    patients*.jsonl   ② (several files allowed)
  --id-map      id_map*.json      patient_id -> base_id (several files allowed)
  --candidates  trial_candidates.jsonl   {"base_id", "trial_ids": [...]}

Outputs (default names, written next to --out):
  gold_draft.jsonl          ④ per pair, label_source "llm" (resumable: done pairs are skipped)
  gold_draft_notes.jsonl    cohort choice, per-criterion rationale, not-applicable criteria, problems, tokens
  ranking_gold_draft.jsonl  draft ranking per patient
  review.csv                one row per criterion for human review (open in Excel; UTF-8 with BOM)

Examples:
  python3 label_gold.py --trials T --criteria C --patients patients.jsonl --id-map id_map.json \
      --candidates trial_candidates.jsonl --dry-run
  python3 label_gold.py ... --provider anthropic --model claude-sonnet-5-5
  python3 label_gold.py ... --provider openrouter --model openai/gpt-oss-120b   # OPENROUTER_API_KEY
  python3 label_gold.py ... --only S002,C001          # some base_ids
  python3 label_gold.py ... --workers 10              # parallel pairs (default 6; 1 = one by one)
  python3 label_gold.py ... --review-only             # rebuild review.csv / ranking from existing drafts
"""
import argparse, csv, json, os, random, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gold_lib as G  # noqa: E402

PROMPT = open(os.path.join(HERE, "prompt_label_gold.md"), encoding="utf-8").read()
PRICES = {"openai/gpt-oss-120b": (0.15, 0.60), "claude-sonnet-5-5": (2, 10), "claude-opus-5-5": (4, 20), "claude-haiku-4-5-20251001": (1, 5)}  # $/M tokens


def patient_text(p):
    lines = [f"patient_id: {p['patient_id']}", f"summary: {p['summary']}", "documents:"]
    for d in p["documents"]:
        try:   # days before as_of, so the model never counts from its own idea of "today"
            ago = (date.fromisoformat(p["as_of"]) - date.fromisoformat(d["date"])).days
            when = f"{d['date']} ({ago} days before as_of)"
        except (KeyError, ValueError, TypeError):
            when = d["date"]
        lines.append(f"--- doc_id: {d['doc_id']} | {when} | {d['type']} | {d['author_role']}\n{d['text']}")
    return "\n".join(lines)


def trial_text(t):
    arms = "; ".join(f"{a.get('label')} ({a.get('type')}): {', '.join(a.get('interventions') or [])}" for a in t.get("arms", []))
    return "\n".join([
        f"trial_id: {t['trial_id']}", f"title: {t.get('title')}", f"phases: {', '.join(t.get('phases') or [])}",
        f"age: {t.get('min_age')} to {t.get('max_age')} years; sex: {t.get('sex')}",
        f"arms: {arms or '-'}",
        f"summary: {(t.get('brief_summary') or '')[:1500]}",
        "note: the published criteria may be incomplete" if t.get("criteria_complete") is False else "",
    ]).strip()


def criteria_text(cs):
    return "\n".join(f"{c['criterion_id']} | {c['type']} | {c.get('cohort') or '-'} | {c['original_text']}" for c in cs)


def check_rows(out, crits, patient):
    """Validate an answer criterion by criterion.
    Returns ({criterion_id: row} that passed, {criterion_id: [problems]} to redo, quote_only set, unknown ids)."""
    want = {c["criterion_id"] for c in crits}
    got = {}
    for c in out.get("criteria", []) or []:
        if isinstance(c, dict) and c.get("criterion_id") in want and c["criterion_id"] not in got:
            got[c["criterion_id"]] = c
    unknown = [c.get("criterion_id") for c in out.get("criteria", []) or [] if isinstance(c, dict) and c.get("criterion_id") not in want]
    ok, redo, quote_only = {}, {}, set()
    for cid in [c["criterion_id"] for c in crits]:
        c = got.get(cid)
        if c is None:
            redo[cid] = ["missing from the answer"]
            continue
        probs = G.check_criterion(c)
        if (c.get("expected_status"), c.get("reason")) in G.NEEDS_EVIDENCE and not c.get("evidence") and c.get("applies", True):
            probs.append(f"{cid}: {c['expected_status']}/{c['reason']} needs at least one quote")
        _, _, q = G.build_gold_evidence([c], patient) if c.get("applies", True) else (None, None, [])
        if probs or q:
            redo[cid] = probs + q
            if not probs:
                quote_only.add(cid)
            got[cid] = c
        else:
            ok[cid] = c
    return ok, redo, quote_only, got, unknown


def make_gold(patient, base_id, trial, rows, sprobs, admin=frozenset()):
    applied = [c for c in rows if c.get("applies", True)]
    gold_ev, per, _ = G.build_gold_evidence(applied, patient)
    crit = [{"criterion_id": c["criterion_id"], "expected_status": c["expected_status"], "reason": c["reason"],
             "supporting_evidence": per.get(c["criterion_id"], []), "decoy_evidence": [],
             "expected_action": c["expected_action"]} for c in applied]
    return {"patient_id": patient["patient_id"], "trial_id": trial["trial_id"], "base_id": base_id, "variant": "base",
            "as_of": patient["as_of"], "label_source": "llm",
            "trial_label": G.trial_label(crit, sprobs, admin),
            "criteria": crit, "gold_evidence": gold_ev, "injection": None}


def judgment(g, cid):
    """(status, reason) of one criterion in a gold record, or ('N/A', '') if it was judged not applicable."""
    x = next((c for c in g["criteria"] if c["criterion_id"] == cid), None)
    return (x["expected_status"], x["reason"]) if x else ("N/A", "")


def write_review(path, golds, notes, crit_by_trial, trials, patients, golds2=None, notes2=None):
    note_by = {(n["patient_id"], n["trial_id"]): n for n in notes}
    g2_by = {(g["patient_id"], g["trial_id"]): g for g in (golds2 or [])}
    n2_by = {(n["patient_id"], n["trial_id"]): n for n in (notes2 or [])}
    cols = ["patient_id", "base_id", "trial_id", "trial_title", "trial_label_llm", "trial_label_llm2", "cohort_assignment", "check",
            "criterion_id", "type", "admin", "cohort", "original_text",
            "llm_status", "llm_reason", "llm_action", "llm_evidence", "llm_rationale",
            "llm2_status", "llm2_reason", "llm2_evidence", "llm2_rationale",
            "review_status", "review_reason", "review_action", "review_evidence", "review_note"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for g in golds:
            key = (g["patient_id"], g["trial_id"])
            n = note_by.get(key, {})
            gc = {c["criterion_id"]: c for c in g["criteria"]}
            ev = {e["gold_ev_id"]: e for e in g["gold_evidence"]}
            g2, n2 = g2_by.get(key), n2_by.get(key, {})
            gc2 = {c["criterion_id"]: c for c in g2["criteria"]} if g2 else {}
            ev2 = {e["gold_ev_id"]: e for e in g2["gold_evidence"]} if g2 else {}
            for c in crit_by_trial.get(g["trial_id"], []):
                cid = c["criterion_id"]
                x = gc.get(cid)
                row = {"patient_id": g["patient_id"], "base_id": g["base_id"], "trial_id": g["trial_id"],
                       "trial_title": trials.get(g["trial_id"], {}).get("title", ""), "trial_label_llm": g["trial_label"],
                       "cohort_assignment": n.get("cohort_assignment") or "", "criterion_id": cid, "type": c["type"],
                       "cohort": c.get("cohort") or "", "original_text": c["original_text"],
                       "admin": "Y" if c.get("administrative") else "",
                       "llm_rationale": n.get("rationale", {}).get(cid, ""),
                       "trial_label_llm2": g2["trial_label"] if g2 else ""}
                flags = []
                if any(p_.startswith(cid + ":") for p_ in n.get("problems", [])):
                    flags.append("quote/auto-fill")
                if cid in n.get("structured", {}):
                    flags.append("age/sex")
                if g2:
                    y = gc2.get(cid)
                    row.update(llm2_status=y["expected_status"] if y else "N/A", llm2_reason=y["reason"] if y else "",
                               llm2_evidence=" | ".join(f"{ev2[i]['doc_id']}: {ev2[i]['text']}" for i in y["supporting_evidence"]) if y else "",
                               llm2_rationale=n2.get("rationale", {}).get(cid, ""))
                    if judgment(g, cid) != judgment(g2, cid):
                        flags.append("runs differ")
                row["check"] = ("CHECK " + ", ".join(flags)) if flags else ""
                if x:
                    row.update(llm_status=x["expected_status"], llm_reason=x["reason"], llm_action=x["expected_action"],
                               llm_evidence=" | ".join(f"{ev[i]['doc_id']}: {ev[i]['text']}" for i in x["supporting_evidence"]))
                else:
                    row.update(llm_status="N/A", llm_reason="", llm_action="", llm_evidence="")
                w.writerow(row)


class FatalAPIError(Exception):
    pass


RETRYABLE = {"RateLimitError", "APIConnectionError", "InternalServerError", "OverloadedError", "ServiceUnavailableError"}


RUNNING = {}   # job key -> start time (for the heartbeat)


def label_pair(a, b, pid, tid, p, t, cs, temperature=None):
    """Label one patient x trial pair. Runs in a worker thread: no file writes, no prints (returns a log)."""
    key = f"{b}/{tid}" + ("" if temperature is None else " (run2)")
    RUNNING[key] = time.time()
    try:
        return _label_pair(a, b, pid, tid, p, t, cs, temperature)
    finally:
        RUNNING.pop(key, None)


def _label_pair(a, b, pid, tid, p, t, cs, temperature=None):
    t0 = time.time()
    log, tok_in, tok_out, cost = [], 0, 0, 0.0
    by_id = {c["criterion_id"]: c for c in cs}
    accepted, fallback, last_seen, redo, out_meta = {}, {}, {}, {c["criterion_id"]: [] for c in cs}, {}
    attempt, api_fail = 0, 0
    while redo and attempt < a.retries:
        attempt += 1
        todo_cs = [by_id[i] for i in by_id if i in redo]
        prompt = PROMPT.format(as_of=p["as_of"], patient=patient_text(p), trial=trial_text(t), criteria=criteria_text(todo_cs))
        if attempt > 1:   # partial repair: only the criteria that were missing or wrong
            fb = [f"- {cid}: {'; '.join(x for x in redo[cid] if x)[:200] or 'missing'}" for cid in redo]
            prompt += ("\n\nThis is a follow-up. Judge ONLY the criteria listed above. Your previous answer had these problems "
                       "(quotes must be exact substrings of the document text, no '...'):\n" + "\n".join(fb[:60]))
        try:
            # cap the answer length to what this many criteria need: a looping model stops early instead of
            # generating until a 32k-token limit (which can take many minutes)
            cap = min(32000, 6000 + 250 * len(todo_cs))
            text, usage = G.call_llm(a.provider, a.model, prompt, a.temperature if temperature is None else temperature,
                                     max_tokens=cap)
        except Exception as e:
            name = type(e).__name__
            if name in G.FATAL_ERRORS:
                raise FatalAPIError(f"{name}: {e}")
            if name in RETRYABLE and api_fail < 5:      # rate limit / overload: back off, do not use up an attempt
                api_fail += 1; attempt -= 1
                wait = min(60, 2 ** api_fail) + random.random()
                log.append(f"  wait {b}/{tid}: {name}, retry in {wait:.0f}s")
                time.sleep(wait)
                continue
            log.append(f"  retry {b}/{tid}: api {name}: {str(e)[:120]}")
            continue
        tok_in += usage["input_tokens"]; tok_out += usage["output_tokens"]
        cost += usage.get("cost") or 0
        try:
            out = G.parse_json(text)
        except Exception as e:
            log.append(f"  retry {b}/{tid}: bad JSON ({e})")
            continue
        if out.get("cohort_assignment") is not None or "cohort_assignment" not in out_meta:
            out_meta["cohort_assignment"] = out.get("cohort_assignment")
        ok, new_redo, quote_only, got, unknown = check_rows(out, todo_cs, p)
        accepted.update(ok)
        last_seen.update(got)
        for cid in quote_only:              # keep as fallback if quotes never match
            fallback[cid] = got[cid]
        redo = new_redo
        if redo:
            log.append(f"  retry {b}/{tid}: {len(redo)} of {len(todo_cs)} criteria to redo"
                       + (f", {len(unknown)} unknown ids ignored" if unknown else "")
                       + f", e.g. {next(iter(redo))}: {(next(iter(redo.values())) or ['?'])[0][:80]}")
    # criteria still wrong only because of quotes are kept (flagged CHECK in review.csv)
    qprobs = []
    for cid in list(redo):
        if cid in fallback:
            accepted[cid] = fallback[cid]
            qprobs += [x for x in redo.pop(cid) if x]
    # a few criteria the model never got right do not sink the whole pair: fill them conservatively and flag CHECK
    if redo and len(redo) <= max(3, len(cs) // 5):
        for cid in list(redo):
            prev = last_seen.get(cid) or {}
            if prev.get("expected_status") == "UNKNOWN" and prev.get("expected_action") in G.ACTIONS - {"none"}:
                row = dict(prev, reason="MISSING", evidence=[])        # e.g. UNSUPPORTED without a usable quote
                why = f"{cid}: auto-filled UNKNOWN/MISSING (model gave {prev.get('reason')} without a usable quote)"
            else:
                row = {"criterion_id": cid, "applies": True, "expected_status": "UNKNOWN", "reason": "MISSING",
                       "evidence": [], "expected_action": "clinician_confirmation",
                       "rationale": "auto-filled: the model did not return a valid judgment"}
                why = f"{cid}: auto-filled UNKNOWN/MISSING (no valid judgment after {attempt} tries)"
            accepted[cid] = row
            qprobs.append(why)
            redo.pop(cid)
        log.append(f"  fill {b}/{tid}: {sum('auto-filled' in q for q in qprobs)} criteria auto-filled, flagged CHECK")
    best = None
    if not redo:
        rows = [accepted[c["criterion_id"]] for c in cs]
        best = (out_meta, rows, qprobs)
    res = {"log": log, "tok_in": tok_in, "tok_out": tok_out, "cost": cost, "gold": None, "note": None,
           "seconds": time.time() - t0}
    if best is None:
        return res
    out, rows, qprobs = best
    sprobs = G.structured_check(p, t)
    res["gold"] = make_gold(p, b, t, rows, sprobs, G.admin_ids(cs))
    res["note"] = {"patient_id": pid, "trial_id": tid, "base_id": b, "provider": a.provider, "model": a.model,
                   "created": date.today().isoformat(), "cohort_assignment": out.get("cohort_assignment"),
                   "not_applicable": [c["criterion_id"] for c in rows if not c.get("applies", True)],
                   "rationale": {c["criterion_id"]: c.get("rationale", "") for c in rows},
                   "problems": qprobs, "structured_problems": sprobs, "attempts": attempt,
                   "seconds": round(res["seconds"], 1), "tokens": {"in": tok_in, "out": tok_out}}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", required=True)
    ap.add_argument("--criteria", required=True)
    ap.add_argument("--patients", nargs="+", required=True)
    ap.add_argument("--id-map", nargs="+", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--provider", choices=["anthropic", "openai", "openrouter"])
    ap.add_argument("--model")
    ap.add_argument("--out", default="gold_draft.jsonl")
    ap.add_argument("--only", help="comma-separated base_ids")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=6, help="pairs labeled in parallel (lower it if you hit rate limits)")
    ap.add_argument("--runs", type=int, choices=[1, 2], default=2,
                    help="2 = label every pair twice independently and flag criteria where the runs differ (default)")
    ap.add_argument("--run2-temperature", type=float, default=0.7,
                    help="temperature of the second run, so it is a real second opinion")
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt and the pair count, call nothing")
    ap.add_argument("--review-only", action="store_true", help="rebuild review.csv and ranking from existing drafts")
    a = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    notes_path = os.path.join(out_dir, "gold_draft_notes.jsonl")
    rank_path = os.path.join(out_dir, "ranking_gold_draft.jsonl")
    review_path = os.path.join(out_dir, "review.csv")

    trials = {t["trial_id"]: t for t in G.load_jsonl(a.trials)}
    crit_by_trial = {}
    for c in G.load_jsonl(a.criteria):
        crit_by_trial.setdefault(c["trial_id"], []).append(c)
    patients = {p["patient_id"]: p for p in G.load_jsonl(a.patients)}
    id_map = G.load_id_maps(a.id_map)
    by_base = {}
    for pid, b in id_map.items():
        if pid in patients:
            by_base.setdefault(b, []).append(pid)
    only = set(a.only.split(",")) if a.only else None

    pairs, skipped = [], []
    for row in G.load_jsonl(a.candidates):
        b = row["base_id"]
        if only and b not in only:
            continue
        if b not in by_base:
            skipped.append(f"{b}: no patient in --patients/--id-map")
            continue
        for pid in sorted(by_base[b]):
            for tid in row.get("trial_ids", []):
                if tid not in trials or tid not in crit_by_trial:
                    skipped.append(f"{b}/{tid}: trial or criteria missing")
                    continue
                pairs.append((b, pid, tid))
    for s in skipped:
        print("SKIP", s)

    out2 = os.path.join(out_dir, "gold_draft.run2.jsonl")
    notes2_path = os.path.join(out_dir, "gold_draft_notes.run2.jsonl")
    files = [(a.out, notes_path), (out2, notes2_path)][:a.runs]
    golds_r = [G.load_jsonl(o) if os.path.exists(o) else [] for o, _ in files]
    notes_r = [G.load_jsonl(n_) if os.path.exists(n_) else [] for _, n_ in files]
    # recompute trial labels with the current rule (drafts made with an older rule are updated in memory and on disk)
    for gs, (path_, _) in (zip(golds_r, files) if not a.dry_run else []):
        changed = 0
        for g in gs:
            new = G.trial_label(g["criteria"], G.structured_check(patients[g["patient_id"]], trials[g["trial_id"]])
                                if g["patient_id"] in patients and g["trial_id"] in trials else (),
                                G.admin_ids(crit_by_trial.get(g["trial_id"], [])))
            changed += new != g["trial_label"]
            g["trial_label"] = new
        if changed:
            G.write_jsonl(path_, gs)
            print(f"trial labels recomputed with the current rule: {changed} changed in {os.path.basename(path_)}")
    golds, notes = golds_r[0], notes_r[0]
    done = {(g["patient_id"], g["trial_id"]) for g in golds}
    done_r = [{(g["patient_id"], g["trial_id"]) for g in gs} for gs in golds_r]

    if a.dry_run:
        n_crit = sum(len(crit_by_trial[t]) for _, _, t in pairs)
        print(f"{len(pairs)} pairs ({len(done & {(p, t) for _, p, t in pairs})} already done), {n_crit} criterion judgments")
        if pairs:
            b, pid, tid = pairs[0]
            print(PROMPT.format(as_of=patients[pid]["as_of"], patient=patient_text(patients[pid]),
                                trial=trial_text(trials[tid]), criteria=criteria_text(crit_by_trial[tid])))
        return

    if not a.review_only:
        if not (a.provider and a.model):
            ap.error("--provider and --model are required (or use --dry-run / --review-only)")
        G.preflight(a.provider)
        todo = [(r, x) for r in range(a.runs) for x in pairs if (x[1], x[2]) not in done_r[r]]
        tok_in = tok_out = 0
        real_cost = 0.0
        t_all = time.time()
        n_ok = n_fail = 0
        print(f"{len(todo)} labeling jobs ({len(pairs)} pairs x {a.runs} run(s), already done skipped) with {a.workers} worker(s)")
        stop_hb = threading.Event()

        def heartbeat():   # every 60 s: what is running and for how long (also in progress.log)
            while not stop_hb.wait(60):
                now = time.time()
                items = sorted(RUNNING.items(), key=lambda kv: kv[1])
                msg = (f"  ... {time.strftime('%H:%M:%S')} {n_ok + n_fail}/{len(todo)} done, {len(items)} running"
                       + (f"; longest {items[0][0]} {now - items[0][1]:.0f}s" if items else ""))
                print(msg, flush=True)
                with open(os.path.join(out_dir, "progress.log"), "a", encoding="utf-8") as f_:
                    f_.write(msg + "\n")

        threading.Thread(target=heartbeat, daemon=True).start()
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = {ex.submit(label_pair, a, b, pid, tid, patients[pid], trials[tid], crit_by_trial[tid],
                              None if r == 0 else a.run2_temperature): (r, b, pid, tid)
                    for r, (b, pid, tid) in todo}
            try:
                for fut in as_completed(futs):
                    r, b, pid, tid = futs[fut]
                    tag = "" if r == 0 else " (run2)"
                    try:
                        res = fut.result()       # FatalAPIError propagates (stops the run)
                    except FatalAPIError:
                        raise
                    except Exception as e:      # any other bug in one pair must not stop the whole run
                        n_fail += 1
                        print(f"FAIL {b} {pid} x {tid}{tag}: {type(e).__name__}: {str(e)[:150]}")
                        continue
                    for m in res["log"]:
                        print(m)
                    tok_in += res["tok_in"]; tok_out += res["tok_out"]; real_cost += res["cost"]
                    if res["gold"] is None:
                        n_fail += 1
                        print(f"FAIL {b} {pid} x {tid}{tag}  ({res['seconds']:.0f}s)")
                        continue
                    g, note = res["gold"], res["note"]
                    note["run"] = r + 1
                    golds_r[r].append(g); notes_r[r].append(note); n_ok += 1
                    with open(files[r][0], "a", encoding="utf-8") as f:       # only the main thread writes
                        f.write(json.dumps(g, ensure_ascii=False) + "\n")
                    with open(files[r][1], "a", encoding="utf-8") as f:
                        f.write(json.dumps(note, ensure_ascii=False) + "\n")
                    cnt = {s_: sum(c["expected_status"] == s_ for c in g["criteria"]) for s_ in ("PASS", "FAIL", "UNKNOWN", "CONFLICT")}
                    sprobs, qprobs = note["structured_problems"], note["problems"]
                    print(f"OK   [{n_ok + n_fail}/{len(todo)}] {b} {pid} x {tid}{tag}: {g['trial_label']:<10} "
                          + " ".join(f"{k}={v}" for k, v in cnt.items()) + f"  ({note['seconds']:.0f}s)"
                          + (f"  ({len(qprobs)} to check)" if qprobs else "") + (f"  STRUCTURED: {sprobs}" if sprobs else ""))
            except FatalAPIError as e:
                for f_ in futs:
                    f_.cancel()
                ex.shutdown(wait=False, cancel_futures=True)
                sys.exit(f"STOP: {e}")
        stop_hb.set()
        print(f"done: {n_ok} ok, {n_fail} failed in {time.time() - t_all:.0f}s")
        price = PRICES.get(a.model)
        if real_cost:
            cost = f", charged ${real_cost:.3f} (OpenRouter)"
        else:
            cost = f", about ${(tok_in * price[0] + tok_out * price[1]) / 1e6:.2f}" if price else ""
        print(f"tokens: {tok_in} in / {tok_out} out{cost}")

    G.write_jsonl(rank_path, G.ranking_rows(golds, trials))
    for n in notes:  # expose structured (age/sex) problems on the first criterion row of the pair
        if n.get("structured_problems") and crit_by_trial.get(n["trial_id"]):
            n["structured"] = {crit_by_trial[n["trial_id"]][0]["criterion_id"]: "; ".join(n["structured_problems"])}
    golds2 = golds_r[1] if a.runs == 2 else []
    write_review(review_path, golds, notes, crit_by_trial, trials, patients, golds2, notes_r[1] if a.runs == 2 else [])
    if golds2:
        g2_by = {(g["patient_id"], g["trial_id"]): g for g in golds2}
        both = [(g, g2_by[(g["patient_id"], g["trial_id"])]) for g in golds if (g["patient_id"], g["trial_id"]) in g2_by]
        n_c = n_same = n_lab = 0
        per_pair = []
        for g1, g2 in both:
            ids = [c["criterion_id"] for c in crit_by_trial[g1["trial_id"]]]
            same = sum(judgment(g1, i) == judgment(g2, i) for i in ids)
            n_c += len(ids); n_same += same; n_lab += g1["trial_label"] == g2["trial_label"]
            per_pair.append({"patient_id": g1["patient_id"], "trial_id": g1["trial_id"], "criteria": len(ids),
                             "differ": len(ids) - same, "trial_label": [g1["trial_label"], g2["trial_label"]]})
        summ = {"pairs_compared": len(both), "criteria_compared": n_c, "criteria_agree": n_same,
                "criteria_agreement": round(n_same / n_c, 3) if n_c else None,
                "trial_label_agreement": round(n_lab / len(both), 3) if both else None, "pairs": per_pair}
        json.dump(summ, open(os.path.join(out_dir, "run_agreement.json"), "w"), indent=1)
        if both:
            print(f"runs agree on {n_same}/{n_c} criteria ({100 * n_same / n_c:.0f}%) and {n_lab}/{len(both)} trial labels; "
                  f"{n_c - n_same} criteria flagged 'CHECK runs differ' in review.csv")
    print(f"{len(golds)} pairs in {a.out}; review sheet -> {review_path}; ranking draft -> {rank_path}")


if __name__ == "__main__":
    main()
