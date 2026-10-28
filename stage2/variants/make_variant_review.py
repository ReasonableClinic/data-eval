#!/usr/bin/env python3
"""Review screen for variants the LLM check disagreed with (open the output in the "정답 검수실" page).
1st judgment = the variant gold (what we propose), 2nd = the blind LLM check. "1차 동의" keeps the gold.
Usage: python3 make_variant_review.py --split dev --dir out_dev [--skip SYN-2408 ...]
"""
import argparse, csv, hashlib, json, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
KO = {"violation": "기준 위반 값으로 바꾼 변형", "missing": "근거를 지운 변형", "expired": "검사 날짜를 기간 밖으로 옮긴 변형",
      "conflict": "다른 출처의 반대 기록을 추가한 변형 (공통 형식 6.3: 출처가 다른 기록이 엇갈리면 CONFLICT)",
      "unsupported": "근거를 지우고 관련은 있지만 입증하지 못하는 기록을 넣은 변형 (결과 대기·내용 불명 = UNSUPPORTED)"}
jl = lambda p: [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]  # noqa: E731
ap = argparse.ArgumentParser(); ap.add_argument("--split", required=True); ap.add_argument("--dir", required=True)
ap.add_argument("--skip", nargs="*", default=[]); a = ap.parse_args()
V = {p["patient_id"]: p for p in jl(os.path.join(a.dir, "patients_variants.jsonl"))}
M = json.load(open(os.path.join(a.dir, "id_map_variants.json")))
GV = [g for g in jl(os.path.join(a.dir, "gold_variants.jsonl")) if (g.get("injection") or {}).get("doc_id")]
C = {c["criterion_id"]: c for c in jl(os.path.join(ROOT, f"ctgov_v2/{a.split}/criteria.jsonl"))}
T = {t["trial_id"]: t for t in jl(os.path.join(ROOT, "ctgov_v1/trials.jsonl"))}
kop = os.path.join(ROOT, "handoff/agent3_review_page/dev_ko.json")
ko = json.load(open(kop, encoding="utf-8")) if os.path.exists(kop) else {}
k = lambda t: ko.get(hashlib.sha1(t.strip().encode()).hexdigest()[:16], "") if t else ""  # noqa: E731
rep = {r["patient_id"]: r for r in csv.DictReader(open(os.path.join(a.dir, "verify_report.csv"), encoding="utf-8-sig"))}
pairs, used = [], set()
for g in GV:
    pid = g["patient_id"]
    r = rep.get(pid)
    if not r or r["agree"] == "Y" or pid in a.skip:
        continue
    cid = M[pid]["target_criterion"]
    c = next(x for x in g["criteria"] if x["criterion_id"] == cid)
    E = {e["gold_ev_id"]: e for e in g["gold_evidence"]}
    ev = " | ".join(f"{E[i]['doc_id']}: {E[i]['text']}" for i in c["supporting_evidence"])
    cr = C[cid]
    title = T[g["trial_id"]]["title"]
    diff = "CHECK runs differ" + (" (상태도 다름)" if r["status_agree"] != "Y" else " (이유만 다름)")
    pairs.append({"key": f"{pid}|{g['trial_id']}", "patient_id": pid, "base_id": f"{M[pid]['base_patient_id']} {M[pid]['variant']}",
                  "trial_id": g["trial_id"], "trial_title": title, "trial_title_ko": k(title),
                  "trial_label_llm": g["trial_label"], "trial_label_llm2": "", "cohort_assignment": "",
                  "rows": [{"criterion_id": cid, "type": cr["type"], "admin": "", "cohort": cr.get("cohort") or "", "check": diff,
                            "original_text": cr["original_text"], "text_ko": k(cr["original_text"]),
                            "llm_status": c["expected_status"], "llm_reason": c["reason"], "llm_action": c["expected_action"],
                            "llm_evidence": ev, "llm_rationale": g["injection"]["note"],
                            "rationale_ko": f"[변형 정답] {KO[M[pid]['variant']]}. 수정 내용: {g['injection']['note']}",
                            "llm2_status": r["llm_status"], "llm2_reason": r["llm_reason"], "llm2_evidence": r["llm_evidence"],
                            "llm2_rationale": r["llm_rationale"], "rationale2_ko": f"[LLM 독립 확인] {r['llm_rationale']}"}]})
    used.add(pid)
bundle = {"version": 1, "run": f"variants_{a.split}_review", "columns": None,
          "patients": {pid: {x: V[pid][x] for x in ("patient_id", "as_of", "summary", "documents")} for pid in used},
          "pairs": pairs}
out = os.path.join(a.dir, "review_bundle_variants.json")
json.dump(bundle, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print(f"{len(pairs)} variants to review -> {out}")
