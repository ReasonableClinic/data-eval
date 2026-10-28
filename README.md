# data-eval — 합성 환자 데이터, 정답, 채점 (비공개)

임상시험 매칭 프로젝트의 합성 환자(②), 정답(④), 변형 세트, 채점 도구를 만드는 레포입니다. 형식은 `docs/common_format_v0.5.md`(공통 형식 v0.5)를 따릅니다.

> **접근은 데이터 담당만.** 에이전트 개발자는 이 레포를 보지 않습니다 (test 정답 원칙). Organization 기본 권한은 No permission, Team_F에도 권한을 주지 않습니다. 팀에 필요한 것(dev 데이터·정답, 채점 스크립트, 키트)은 `make_handoff.py` 등이 만든 zip으로 전달합니다.

## 레포에 있는 것과 없는 것

`.gitignore`가 화이트리스트라 **코드와 문서만** 올라갑니다 (약 53개). 데이터와 결과는 로컬 작업 폴더에만 있습니다.

| 구분 | 무엇 | git |
| --- | --- | --- |
| 코드·문서 | `datakit.py`, `validate.py`, `make_handoff.py`, `stage2/` 스크립트·프롬프트·README, `generation/` 스크립트·프롬프트, `docs/` | 올림 |
| 데이터 (로컬 전용) | 환자 파일, `ctgov_v1/`, `ctgov_v2/`, `stage2/runs/`(정답 전 버전), 변형 결과 `stage2/variants/out_*`·`final_*`, TREC·TrialGPT 데이터, `handoff/` zip | 안 올림 |
| 비공개 설계 | test 변형 수정안(`make_edits_test.py`, `edits_test.json`, `plan_test*`), `stage2/variants/README.md`(test 변형 대상이 적힌 작업 기록), `generation/` specs·기록·로그, `id_map*`, `*private*` | 안 올림 |
| 다른 담당과 주고받은 것 | `agent2_workspace/`, `agent3_workspace/`, `agent5_workspace/` | 안 올림 |
| 키·캐시 | `.env`, `.venv/`, `__pycache__/`, `stage2/ko_cache.json`, `*.bak` | 안 올림 |

**데이터는 git에 없으니 따로 백업합니다.** 로컬 폴더가 원본입니다. 정답을 고친 뒤에는 `handoff/` zip을 다시 만들고, 폴더 전체(특히 `stage2/runs/`, `stage2/variants/`, `ctgov_v2/`, 환자 파일, `id_map*`)를 비공개 저장소에 백업합니다.

새 PC에서 이어서 작업할 때: 이 레포를 받은 뒤, 백업한 데이터 폴더를 같은 경로 구조로 덮어씁니다 (아래 "폴더").

## 현재 상태 (2026-10-28)

| 항목 | 버전 | 위치 (로컬) |
| --- | --- | --- |
| dev 환자 20명 / test 환자 30명 | as_of 2026-10-01, 국적 전원 South Korea | `patients_v2.jsonl`, `patients_eval_v2.jsonl`, `topics*.json` |
| dev 정답 54쌍 | dev_v10, 시험 판정 eligible 5 / potential 15 / ineligible 34 | `stage2/runs/dev_v10/` |
| test 정답 90쌍 | test_v9, 9 / 30 / 51 | `stage2/runs/test_v9/` |
| 변형 세트 | dev 36명·100쌍, test 34명·102쌍 | `stage2/variants/final_dev/`, `final_test/` |
| ①-b 기준 | dev v2 final + 우리 쪽 보정, test v1 + 보정 (`fix_ctgov_units.py`) | `ctgov_v2/dev/`, `ctgov_v2/test/` |
| 팀 전달 zip | `synthetic_dev_v10`, `synthetic_test_v11`(비공개), `for_agent3_v10`, `for_agent456_v5`, `eval_tools_v1`, `backend_skeleton_v1` | `handoff/` |

모든 정답은 `label_source: "human_verified"`. 버전별 변경은 `docs/CHANGELOG.md`.

## 폴더

```
data-eval/                      (★ = git에 올라감, 나머지는 로컬 전용)
├─ README.md ★, .gitignore ★
├─ datakit.py ★                 도구 목록·실행
├─ validate.py ★                ② 환자 기록 형식 검사
├─ make_handoff.py ★            정답 → 팀 전달 zip
├─ docs/ ★                      공통 형식 v0.5, CHANGELOG, 에이전트 3 메모, ctgov_request/
├─ generation/                  1단계 환자 생성 (스크립트·프롬프트 ★, specs·기록은 로컬)
├─ stage2/                      정답 달기·검수·수정, CT.gov 보정 (스크립트 ★)
│   ├─ runs/                    정답 전 버전 dev_v3…v10, test_v3…v9, gold_fixes_*.csv, test 채점 결과
│   ├─ variants/                변형 세트 (스크립트 ★, out_*/final_*/edits는 로컬)
│   ├─ agent456/                에이전트 4·5·6 키트 만들기, 변형 채점 스크립트 ★
│   └─ trec_eval/               TREC·TrialGPT 비교 (스크립트 ★, 데이터는 로컬)
├─ patients_v2.jsonl, patients_eval_v2.jsonl, topics*.json, id_map*.json
├─ ctgov_v1/, ctgov_v2/         시험·기준 (에이전트 1 결과 + 우리 보정)
├─ handoff/                     팀 전달 zip
├─ agent2_workspace/, agent3_workspace/, agent5_workspace/   받은 버전·검토 메모
└─ _archive/                    옛 버전과 백업
```

## 도구 (`datakit.py`)

스크립트는 원래 폴더에서 돌아가고, 경로 인자는 목록에 나온 `cwd` 기준입니다 (정답 도구 `stage2/`, 변형 도구 `stage2/variants/`).

```
python3 datakit.py                 # 그룹별 명령 목록 (생성, 형식 검사, CT.gov, 정답, 변형, 인계, 채점)
python3 datakit.py selfcheck       # dev·test 환자 형식 + 변형 세트 구조 (API 없음)
```

LLM을 부르는 도구(`label_gold`, `adjudicate`, `fill_gold_evidence`, `make_review_bundle`, `classify_admin`, `verify_variants`, `generation/*`)는 키를 환경변수로 읽습니다 (`stage2/gold_lib.py`, `generation/generate_patients.py`). 키는 셸에서 `export`하거나 `.env`에 두고(`.env`는 git에 안 올라감), 대화·노션에 붙이지 않습니다.

## 정답을 고칠 때

1. 고칠 행을 `stage2/runs/gold_fixes_<split>_MMDD.csv`로 작성 (`old`에 지금 값을 적어 엇갈리면 건너뜀)
2. `python3 datakit.py gold-apply-fixes --run-in runs/<split>_vN --run-out runs/<split>_vN+1 --fixes ... --date ... --patients ...`
3. `stage2/variants/build_variants.py`, `check_variants.py`, `select_targets.py`, `make_handoff.py`의 `SETS`를 새 버전으로 바꾸고 변형 다시 만들기 (`var-build` → `var-check` → `var-finalize`)
4. `python3 make_handoff.py` (test가 바뀌면 `ZIP_VER`의 test 버전을 올림. 내용이 같은 zip은 이전 파일을 그대로 둬서 받은 사람의 바이트 비교가 유지되게)
5. `python3 datakit.py selfcheck`, `docs/CHANGELOG.md`와 이 README의 "현재 상태" 갱신, 커밋, 데이터 백업

## 공개 범위

- **팀에 줘도 되는 것**: dev 환자·정답·변형, test 환자 입력(정답 없이), 채점 스크립트, 키트 zip
- **아무에게도 주지 않는 것**: test 정답(`synthetic_test_v11.zip` 포함), test 변형 대상·수정안, `id_maps_private.zip`, test 채점 결과(`stage2/runs/agent3_test_scores_*`)
- test에서 찾은 에이전트 문제를 개발자에게 알릴 때는 출처(test)를 밝히고, 이후 test 점수는 "test 반영 후"로 따로 기록

## 다른 담당과 주고받기

| 담당 | 받은 것 / 보낸 것 |
| --- | --- |
| 에이전트 1 (CT.gov) | ①-b 원본 `ctgov_v2/received/`, 검토·보정 요청 `docs/ctgov_request/` |
| 에이전트 2 | `agent2_workspace/README.md` (받은 버전 `received/`, 제안 `handoff/for_agent2_*.zip`) |
| 에이전트 3 | `agent3_workspace/README.md` (확정판 a3-0.3.0, test 실행 결과) |
| 에이전트 4·5·6 | `handoff/for_agent456_v5.zip`, 받은 코드 `agent5_workspace/` |
| backend 레포 | 뼈대 `handoff/backend_skeleton_v1.zip`, 공통 형식은 `docs/common_format_v0.5.md`가 원본 |

## 남은 일

- test 정답 재검토 후보 3행 (SYN-1574 NCT07323654-E05, SYN-5887 NCT07640932-E11, SYN-8397 NCT07244835-E04) 결정, 바꾸면 test_v10
- dev 정답 행동 2행 (SYN-0002 NCT07774247-I03·I04, EXPIRED인데 `patient_question` → `new_test` 또는 `clinician_confirmation`), 바꾸면 dev_v11
- 공통 형식 검사기(근거, 판정, 카드) → backend `schemas/`
- 에이전트 5 고리 평가용 정답 키 (dev 변형의 기록 없음·기간 지남 유형, 기본 환자 원래 문서로 답 만들기) — 회의 결정 후
- `stage2/gold_lib.py`가 `.env`를 읽게 (backend `common/env_setup.py`와 같은 방식)
