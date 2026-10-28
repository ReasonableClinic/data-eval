#!/usr/bin/env python3
"""Build the team handoff zips from the final synthetic data.

  handoff/synthetic_dev_v10.zip, handoff/synthetic_test_v11.zip   patients + reference trials/criteria + gold + README
  handoff/id_maps_private.zip                                    patient_id -> base patient id (keep private)
  handoff/for_agent3_v10.zip      one zip for agent developers: dev with gold + test inputs only (no test gold)

Usage (this folder):  python3 make_handoff.py
"""
import collections, json, os, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = {"dev": ("patients_v2.jsonl", "stage2/runs/dev_v10", "Claude Opus"),
        "test": ("patients_eval_v2.jsonl", "stage2/runs/test_v9", "Claude Sonnet 5.5")}
ZIP_VER = {"dev": "v10", "test": "v11"}     # test v11 (2026-10-27): 7 lab-recency rows of test_v7 reverted (test_v9)

README = """# 합성 세트 {name} (공통 형식 v0.5)

합성 환자 {n_p}명과 사람 검수를 마친 정답입니다. 기준일 `as_of`는 모두 2026-10-01, 국적은 모두 `"South Korea"`입니다.

## 폴더

| 경로 | 내용 | 에이전트에 넘김 |
| --- | --- | --- |
| `input/patients.jsonl` | ② 환자 {n_p}명, 문서 {n_d}개 | O |
| `input/topics.json` | 대회 형식 `{{"topics": [{{"num", "title"}}]}}` (`summary`) | O |
| `reference/trials.jsonl` | ⓪ 시험 {n_t}개 (정답 대상 {n_lab}개 + 추천 후보 풀). CT.gov 수집본 그대로 | O |
| `reference/criteria.jsonl` | 기준 {n_c}개 (위 시험의 기준). `administrative` 표시 포함, ①-b 채워짐 (dev v2 확정본, test v1. test 5행은 합성 담당이 단위 정리, `fix_note` 참고) | O |
| `reference/concepts.json` | 개념 사전 (①-b·③·정답 근거가 같이 씀) | O |
| `gold/gold.jsonl` | ④ 환자-시험 {n_g}쌍 | X (채점용) |
| `gold/ranking_gold.jsonl` | 환자별 추천 순위 정답 | X (채점용) |
| `gold/trial_candidates.jsonl` | 기본 환자별 정답 대상 시험(`trial_ids`)과 후보 풀(`pool_trial_ids`) | X (채점용) |
| `gold/gold_review_log.jsonl` | 검수에서 LLM 판정을 바꾼 내역 {n_log}건 | X |
| `common_format_v0.5.md` | 공통 형식 문서 | |

`gold/` 폴더는 에이전트 입력에 넣지 마세요. 환자 번호와 기본 환자 ID의 대응표(`id_map`)는 이 묶음에 없고 합성 담당이 따로 보관합니다.

## 정답 요약

- 시험 판정: {labels}
- 기준 판정 {n_crit}개: {statuses}
- 기준 출처(`review`): {reviews} (`human` 사람 검수, `agreed` LLM 두 번 일치로 인정)
- 모든 쌍이 `label_source: "human_verified"` (뜻은 공통 형식 6.2)
- 후보 풀 시험은 정답이 없으므로 채점에서 unjudged로 처리합니다 (공통 형식 8장)

## 정답을 만든 방법

1. LLM(gpt-oss-120b)이 쌍마다 두 번 판정 (temperature 0, 0.7)
2. 두 판정이 다르거나 근거 인용에 문제가 있는 기준과 시험 판정이 갈린 쌍을 심판 LLM이 다시 판정 ({judge})
3. 사람이 웹 검수 화면에서 위 기준과 FAIL 기준을 모두 검수
4. 시험 판정은 공통 형식 6.1 규칙으로 계산

## 주의

- 모든 기록은 가상입니다. 실제 환자 정보는 없습니다.
- 임상 내용과 정답은 의료진 검토를 거치지 않았습니다.
- 기준 ID는 `reference/criteria.jsonl` 것에 묶여 있습니다. ①-b를 채울 때 기준을 다시 나누지 마세요.
"""


AGENT_README = """# 합성 세트: 에이전트 개발용 (공통 형식 v0.5)

에이전트 개발에 쓸 합성 환자와 시험입니다. 형식은 `common_format_v0.5.md`를 보세요.

## 폴더

| 경로 | 내용 | 용도 |
| --- | --- | --- |
| `dev/input/` | 환자 {dev[patients]}명 (`patients.jsonl`), 대회 형식 `topics.json`, 판정할 쌍 목록 `pairs.jsonl` | 에이전트 입력 |
| `dev/reference/` | 시험 {dev[trials]}개, 기준 {dev[criteria]}개 (정답 대상 + 추천 후보 풀) | 에이전트가 검색·판정할 시험 |
| `dev/gold/` | 정답 {dev[pairs]}쌍 ({dev[labels]}), 순위 정답, 후보 목록, 검수 내역 | 개발 중 채점·오류 분석 |
| `test/input/` | 환자 {test[patients]}명, 판정할 쌍 목록 `pairs.jsonl` (정답 없음) | 최종 평가 입력 |
| `test/reference/` | 시험 {test[trials]}개, 기준 {test[criteria]}개 | 최종 평가 시험 |

**test 정답은 들어 있지 않습니다.** 최종 평가 때 합성 담당이 채점합니다. 프롬프트·규칙은 dev로만 고쳐 주세요. test 환자 기록도 개발 중에는 열어 보지 않는 것을 권합니다.

## 알아둘 점

- 기준일 `as_of`는 모두 2026-10-01. 모든 기간 계산은 실행하는 날이 아니라 `as_of` 기준입니다.
- 정답은 모두 `label_source: "human_verified"`. 기준마다 `review`가 `human`(사람 검수) 또는 `agreed`(LLM 두 번 일치로 인정)입니다.
- 시험 판정 규칙은 공통 형식 6.1, 순위 규칙은 6.4 (오래 확인되지 않은 시험 처리 포함).
- `reference/`의 시험 중 정답이 없는 후보 풀 시험은 채점에서 unjudged로 처리합니다.
- dev·test `reference/criteria.jsonl`에는 CT.gov 담당의 ①-b(`concept`·`operator`·`value`·`time_window`·`logic_group` 등)가 채워져 있고, 개념 사전은 `reference/concepts.json`입니다. 정답 근거(`gold_evidence`)에는 `concept`·`term`·`value`·`unit`·`status`가 채워져 있습니다.
- dev 정답 근거(`gold_evidence`)에 `concept`·`term`·`value`·`unit`·`status`가 채워져 있습니다 (745개 중 706개. 사실이 아닌 문장 38개와 1개는 비어 있음).
- 기준 ID는 `reference/criteria.jsonl` 것에 묶여 있습니다.
- TREC 세트는 TREC 담당의 파일을 쓰세요. 2021년 시험이라 이 시험 파일과 합치면 안 됩니다.
- 모든 기록은 가상이며, 임상 내용과 정답은 의료진 검토를 거치지 않았습니다.
"""


def jl(p):
    return [json.loads(line) for line in open(os.path.join(HERE, p), encoding="utf-8")]


def dump(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def fmt_counter(c):
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items()))


def main():
    trials = {t["trial_id"]: t for t in jl("ctgov_v1/trials.jsonl")}
    crit = jl("ctgov_v1/criteria.jsonl")
    # ①-b (structured criteria) where it has arrived; ids and original_text are the same as ctgov_v1
    for part in ("dev", "test"):
        f = os.path.join(HERE, f"ctgov_v2/{part}/criteria.jsonl")
        if os.path.exists(f):
            v2 = {c["criterion_id"]: c for c in jl(f"ctgov_v2/{part}/criteria.jsonl")}
            crit = [v2.get(c["criterion_id"], c) for c in crit]
    concepts_path = os.path.join(HERE, "ctgov_v2/dev/concepts.json")
    concepts_txt = open(concepts_path, encoding="utf-8").read() if os.path.exists(concepts_path) else None
    cands = jl("ctgov_v1/trial_candidates.jsonl")
    fmt = open(os.path.join(HERE, "docs/common_format_v0.5.md"), encoding="utf-8").read()
    os.makedirs(os.path.join(HERE, "handoff"), exist_ok=True)
    sets_files = {}
    for name, (pfile, run, judge) in SETS.items():
        P, G, R, L = jl(pfile), jl(f"{run}/gold.jsonl"), jl(f"{run}/ranking_gold.jsonl"), jl(f"{run}/gold_review_log.jsonl")
        C = [c for c in cands if c.get("split") == name]
        lab = {t for c in C for t in c["trial_ids"]}
        pool = {t for c in C for t in c.get("pool_trial_ids", [])}
        assert {g["trial_id"] for g in G} <= lab, "a gold trial is missing from trial_candidates"
        not_verified = [g for g in G if g["label_source"] != "human_verified"]
        if not_verified:
            print(f"WARN {name}: {len(not_verified)} pairs are not human_verified")
        tids = sorted((lab | pool) & trials.keys())
        T, CR = [trials[t] for t in tids], [c for c in crit if c["trial_id"] in set(tids)]
        crits = [c for g in G for c in g["criteria"]]
        readme = README.format(
            name=name, n_p=len(P), n_d=sum(len(p["documents"]) for p in P), n_t=len(T), n_lab=len(lab), n_c=len(CR),
            n_g=len(G), n_log=len(L), labels=fmt_counter(collections.Counter(g["trial_label"] for g in G)),
            n_crit=len(crits), statuses=fmt_counter(collections.Counter(c["expected_status"] for c in crits)),
            reviews=fmt_counter(collections.Counter(c.get("review", "?") for c in crits)), judge=judge)
        files = {
            "README.md": readme,
            "common_format_v0.5.md": fmt,
            "input/patients.jsonl": dump(P),
            "input/topics.json": json.dumps({"topics": [{"num": p["patient_id"], "title": p["summary"]} for p in P]},
                                            ensure_ascii=False, indent=1),
            "input/pairs.jsonl": dump([{"patient_id": pid, "trial_ids": sorted(g["trial_id"] for g in G if g["patient_id"] == pid)}
                                       for pid in sorted({g["patient_id"] for g in G})]),
            "reference/trials.jsonl": dump(T),
            "reference/criteria.jsonl": dump(CR),
            **({"reference/concepts.json": concepts_txt} if concepts_txt else {}),
            "gold/gold.jsonl": dump(G),
            "gold/ranking_gold.jsonl": dump(R),
            "gold/trial_candidates.jsonl": dump(C),
            "gold/gold_review_log.jsonl": dump(L),
        }
        # variant set (common format 7): new patients made from this split's base patients; the map stays private
        vdir = os.path.join(HERE, f"stage2/variants/final_{name}")
        if os.path.isdir(vdir):
            files["input/patients_variants.jsonl"] = open(os.path.join(vdir, "patients_variants.jsonl"), encoding="utf-8").read()
            files["input/pairs_variants.jsonl"] = open(os.path.join(vdir, "pairs_variants.jsonl"), encoding="utf-8").read()
            files["gold/gold_variants.jsonl"] = open(os.path.join(vdir, "gold_variants.jsonl"), encoding="utf-8").read()
        sets_files[name] = (files, dict(patients=len(P), pairs=len(G), trials=len(T), criteria=len(CR),
                                        labels=fmt_counter(collections.Counter(g["trial_label"] for g in G))))
        ver = ZIP_VER[name]
        root = f"synthetic_{name}_{ver}/"
        out = os.path.join(HERE, f"handoff/synthetic_{name}_{ver}.zip")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for path, data in files.items():
                z.writestr(root + path, data)
        print(f"{name}: {len(P)} patients, {len(G)} pairs, {len(T)} trials, {len(CR)} criteria -> {out}")
    with zipfile.ZipFile(os.path.join(HERE, "handoff/id_maps_private.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(HERE, "id_map.json"), "id_maps_private/id_map_dev.json")
        z.write(os.path.join(HERE, "id_map_eval.json"), "id_maps_private/id_map_test.json")
        for split in ("dev", "test"):
            f = os.path.join(HERE, f"stage2/variants/final_{split}/id_map_variants_private.json")
            if os.path.exists(f):
                z.write(f, f"id_maps_private/id_map_variants_{split}.json")
        z.writestr("id_maps_private/README.md",
                   "# 환자 번호 대응표 (비공개)\n\n`patient_id` → 기본 환자 ID(S001, C001, E001 등). 기본 환자 ID는 사양(질환·병력)과 "
                   "연결되므로 에이전트 입력이나 공유 폴더에 넣지 마세요. 변형 세트를 만들 때와 오류 분석 때만 씁니다.\n")
    print("id maps -> handoff/id_maps_private.zip")

    # one zip for the agent developers: dev complete, test without anything that reveals the answers
    dev_files, dev_n = sets_files["dev"]
    test_files, test_n = sets_files["test"]
    out = os.path.join(HERE, "handoff/for_agent3_v10.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        root = "for_agent3_v10/"
        z.writestr(root + "README.md", AGENT_README.format(dev=dev_n, test=test_n))
        z.writestr(root + "common_format_v0.5.md", fmt)
        for path, data in dev_files.items():
            if path not in ("README.md", "common_format_v0.5.md"):
                z.writestr(root + "dev/" + path, data)
        for path, data in test_files.items():
            if path.startswith(("input/", "reference/")):
                z.writestr(root + "test/" + path, data)
        z.write(os.path.join(HERE, "docs/AGENT3_NOTES_trialgpt.md"), root + "AGENT3_NOTES_trialgpt.md")
        z.write(os.path.join(HERE, "stage2/runs/audit_dev_missing.csv"), root + "dev/gold/audit_dev_missing.csv")
    print(f"agent developers -> {out} (test gold left out)")


if __name__ == "__main__":
    main()
