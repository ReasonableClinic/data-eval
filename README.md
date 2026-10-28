# 합성 환자 데이터와 정답 (②·④ 담당)

환자-임상시험 매칭 프로젝트의 합성 세트입니다. 형식은 `docs/common_format_v0.5.md`를 따릅니다.
에이전트 2(근거 추출)는 다른 계정에서 작업하므로 `agent2_workspace/`에 따로 둡니다 (아래 "에이전트 2").

## 최종 결과물

| 무엇 | 어디 |
| --- | --- |
| 팀에 넘길 묶음 | `handoff/synthetic_dev_v10.zip`, `handoff/synthetic_test_v11.zip` |
| 에이전트 3 담당에게 넘길 묶음 | `handoff/for_agent3_v10.zip` + `agent2_workspace/received/agent3_kit_v14_12.zip`(dev 근거 v14.12, 2026-10-27) + test 근거 `handoff/agent3_test_kit_v14_9.zip`, 외부 검증 도구 `handoff/eval_tools_v1.zip`, 검수 화면 도구 `handoff/agent3_review_page_v1.zip` |
| 환자 번호 대응표 (비공개, 넘기지 않음) | `handoff/id_maps_private.zip` |
| dev 환자 20명 | `patients_v2.jsonl`, `topics.json` |
| test 환자 30명 | `patients_eval_v2.jsonl`, `topics_eval.json` |
| dev 정답 54쌍 | `stage2/runs/dev_v10/gold.jsonl`, `ranking_gold.jsonl` |
| test 정답 90쌍 | `stage2/runs/test_v9/gold.jsonl`, `ranking_gold.jsonl` |
| 놓친 사실 점검표 | `stage2/runs/audit_dev_missing.csv`, `audit_test_missing.csv` |

두 세트 모두 `label_source: "human_verified"`, 기준일 `as_of` 2026-10-01, 국적 전원 `"South Korea"`.
v4 = 검수 정답(v3) + 놓친 사실 점검 1번 분류 반영 (2026-10-06). dev_v8 = dev_v4 + Agent 3 v1 검토에서 나온 정답 5행 수정 (2026-10-08, `stage2/runs/gold_fixes_dev_1008.csv`). 2026-10-09: 정답 재검토 18행 반영(9행 PASS → UNKNOWN, 시험 판정 불변, `stage2/runs/recheck_1009/`). ①-b(`ctgov_v2/dev/`)로 dev 정답 근거 706개에 개념·값을 채움 (`fill_gold_evidence.py`, 원본 `gold.before_fill.jsonl`). 2026-10-25: dev_v9 = A1 일괄 부정(dev_v8) + A3 나열 항목 규칙 10행 (`gold_fixes_dev_1025.csv`). test_v7 = A1(test_v5) + A3 10행·행정 항목 기준 4행 (`gold_fixes_test_1025.csv`) + 검사 최근성 7행 (`gold_fixes_test_1025b.csv`, 시험 판정 3쌍 eligible → potential). 고치는 스크립트 `stage2/apply_gold_fixes.py`. 2026-10-26: dev_v10·test_v8 = 이유 표기 5행(MISSING → UNSUPPORTED), test 행정 표시 1행, 기록 문구 2곳(SYN-0011·SYN-6332, 같은 길이) + 변형 환자 문서 번호를 날짜 순서로 (원본은 `_archive/patients_before_1026/`, `_archive/variants_1026/`). 에이전트 2 전달 `handoff/for_agent2_1026.zip`. 시험 판정 dev 5/15/34, test 6/33/51. 2026-10-27: test_v9 = test_v8에서 검사 최근성 7행(test_v7)을 되돌림. 새 검사 보고서에 같은 값이 다시 나온 것을 옛 값으로 묶은 착오(`gold_fixes_test_1027.csv`, 공통 형식 6.3 보완). test 시험 판정 9/30/51, test 변형 다시 만듦, `handoff/synthetic_test_v11.zip`(dev·에이전트 3 zip은 그대로). 2026-10-27: 도구 목록·실행 `datakit.py`, 리포용 `.gitignore`(아래 "깃 리포에 올릴 때"), 에이전트 2에 .env·추적 제안 `handoff/for_agent2_1027.zip`. 정답을 고치면 `python3 make_handoff.py`로 zip을 다시 만드세요.

## 폴더

```
stage1_patients/
├─ README.md                 이 파일
├─ docs/                     공통 형식 v0.5 (+ 노션 붙여넣기용), 에이전트 3 메모, ctgov_request/ (CT.gov 담당 요청서)
├─ handoff/                  팀에 넘길 zip (make_handoff.py로 다시 만듦)
├─ datakit.py               도구 목록·실행 (python3 datakit.py)
├─ .gitignore               리포에 올릴 파일 화이트리스트
├─ make_handoff.py           최종 데이터 → handoff zip
├─ validate.py               ② 형식 검사 (python3 validate.py patients_v2.jsonl)
├─ patients_v2.jsonl, patients_eval_v2.jsonl   최종 환자 (dev, test)
├─ topics.json, topics_eval.json               대회 형식 요약
├─ id_map.json, id_map_eval.json               환자 번호 → 기본 환자 ID (에이전트에 넘기지 않음)
├─ ctgov_v1/                 시험(⓪)·기준(①-a)·후보 목록
├─ stage2/                   정답 달기 스크립트와 결과
│   └─ runs/  dev_v3, test_v3 (LLM 초안·심판·검수 원본) → dev_v4 → … → dev_v10, test_v4 → … → test_v9 (최종 정답)
├─ generation/               1단계 환자 생성 코드와 보강 전 환자 (다시 돌릴 일 없음, 기록용)
├─ agent2_workspace/         에이전트 2 (다른 계정) 관련: 검토 메모, 받은 버전
└─ _archive/                 옛 버전과 백업 (필요 없으면 폴더째 지워도 됨)
```

## 도구 실행 (`datakit.py`)

흩어진 스크립트를 한곳에서 찾고 실행하는 목록입니다. 스크립트는 옮기지 않았고, 각자 원래 실행하던 폴더에서 돌아갑니다.

```
python3 datakit.py                 # 그룹별 명령 목록 (생성, 형식 검사, CT.gov, 정답, 변형, 인계, 채점)
python3 datakit.py selfcheck       # 최종 환자 dev·test 형식 + 변형 세트 구조 검사 (API 호출 없음)
python3 datakit.py var-check --split dev --dir out_dev
python3 datakit.py gold-apply-fixes --run-in runs/dev_v10 --run-out runs/dev_v11 --fixes runs/gold_fixes_dev_MMDD.csv --date 2026-MM-DD --patients ../patients_v2.jsonl
```

경로 인자는 목록에 나온 `cwd` 기준입니다 (예: 정답 도구는 `stage2/`, 변형 도구는 `stage2/variants/`). 새 스크립트를 만들면 `datakit.py`의 `COMMANDS`에 한 줄 추가합니다.

## 깃 리포에 올릴 때

이 폴더를 그대로 리포 루트로 쓸 수 있게 `.gitignore`를 화이트리스트로 만들어 두었습니다. 코드와 문서만 올라가고, 데이터는 지금처럼 `handoff/` zip으로만 전달합니다.

| 구분 | 무엇 | 리포 |
| --- | --- | --- |
| 공개 | `datakit.py`, `validate.py`, `make_handoff.py`, `stage2/` 스크립트·프롬프트·README, `generation/` 스크립트·프롬프트, `docs/` | 올림 |
| 데이터 (zip으로 전달) | 환자 파일, `ctgov_v1/`, `ctgov_v2/`, `stage2/runs/`(dev 정답 포함), 변형 결과, TREC·TrialGPT 데이터 | 안 올림 |
| 비공개 (팀원에게도 안 줌) | test 정답(`stage2/runs/test_*`, `variants/*test*`, `make_edits_test.py`, `edits_test.json`, `plan_test*`), `id_map*`, `*private*`, `generation/` specs·기록·로그, `variants/README.md`(test 변형 대상이 적힌 작업 기록) | 안 올림 |
| 다른 담당 | `agent2_workspace/`, `agent3_workspace/` | 안 올림 |
| 키·캐시 | `.env`, `.venv/`, `__pycache__/`, `ko_cache.json`, `*.bak` | 안 올림 |

올리기 전에 `git status --ignored`로 한 번 확인합니다. 빈 파일로 이 폴더 구조를 흉내 내서 확인했을 때 53개 파일(코드·문서·fixtures, .gitignore 포함)만 올라가고, test 정답·ID 대응표·.env는 빠졌습니다 (2026-10-27).

## 에이전트에 넘기면 안 되는 파일

`id_map*.json`, `generation/` (specs, records), `stage2/runs/*` (정답·검수 결과). 환자 입력은 `patients_v2.jsonl`, `patients_eval_v2.jsonl`, `topics*.json`만 씁니다.

## 에이전트 2

`agent2_workspace/README.md`를 보세요. 이 폴더는 다른 계정과 주고받는 파일만 두고, 합성 데이터 쪽 스크립트는 여기서 읽지 않습니다.

## 다음에 할 일

- CT.gov 담당의 ①-b가 오면: 기준 ID가 `ctgov_v1/criteria.jsonl`과 같은지 확인(`stage2/check_concepts.py --ref-criteria`)한 뒤 근거 채우기와 3단계(표적 변형)
- 팀이 일괄 부정 규칙(공통 형식 6.3 제안)을 확정하면 `stage2/audit_patch.py --tiers 1_explicit 2_blanket`로 dev·test 정답 갱신
- 정답 다는 방법은 `stage2/README.md`

- `handoff/for_agent456_v5.zip` (2026-10-27): 에이전트 4·5·6 개발용. dev 기본·변형 환자, 정답(dev_v10), 순위 정답(변형 포함), 에이전트 2 근거 v14.9, 에이전트 3 확정판 a3-0.3.0의 dev 기본 54쌍·변형 100쌍 출력(근거 ID 일치), 변형 채점 스크립트. 만드는 법 `python3 stage2/agent456/make_agent456_kit.py` (이전 판 `_archive/for_agent456_v4.zip`)
