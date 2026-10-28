# ①-b dev v1 검토 (합성 데이터 담당 → CT.gov 담당)

2026-10-09. 대상: `dev_v1_1b.zip` (criteria.jsonl 3,856줄, concepts.json 137개). 저장 위치: `ctgov_v2/dev/`.

## 1. 확인 결과

| 항목 | 결과 |
| --- | --- |
| 기준 ID·원문 | 3,856줄 모두 `ctgov_v1/criteria.jsonl`과 같음 (빠짐·추가·원문 변경 0). 정답 ④와 호환 |
| 남은 오류 60건 | 규칙을 정해 58건 해소 (2장). 진짜 오류 2건만 남음 |
| 근거 채우기 준비 | `fill_gold_evidence.py`가 새 concepts.json·①-b `term`으로 정답 근거 745개를 채울 수 있음 (dry-run 확인) |

## 2. 오류 60건 규칙 (check_concepts.py 반영)

- **(a) 상대 단위 xULN 41건**: 오류가 아니라 "상대 단위"로 집계. 판정은 환자 검사 줄에 적힌 참고 범위 상한으로 계산 (예: "ALT 60 U/L (7-56)" → 60/56 = 1.07×ULN). 참고 범위가 적혀 있지 않으면 UNKNOWN/UNSUPPORTED + `lab_check`. 공통 형식 6.3 "검사지의 참고 범위로 판정"과 같은 원칙
- **(b) 기본 단위가 없는 바구니 검사(`lab_other`, `biomarker`) 14건**: 단위 검사를 건너뛰고 원문 단위를 그대로 둠 (경고만)
- **(c) 변화량 기준(`change: true`) 3건**: `%`, `fold` 단위 허용
- **남은 진짜 오류 2건 (고쳐 주세요)**
  - `NCT07655700-I03` "4 or more migraine attacks per month": 발작 횟수인데 `monthly_migraine_days`(일수)로 들어감. 발작 횟수 개념 키를 새로 만들거나 `symptom_finding` + term으로
  - `NCT07594145-I07` "UACR > 30 mg/dl": 원문 단위가 오타로 보임(UACR은 mg/g). 원문은 그대로 두고 `unit: "mg/g"` + 메모를 권함

## 3. 고쳐 주셨으면 하는 것

1. **`administrative`가 null인 줄 2,711개**: true/false로 채워 주세요. 공통 형식 3장에서 필수 필드이고, 시험 판정 규칙(6.1)이 이 값을 씁니다. 지금은 true 97, false 1,048
2. **`logic_group`이 기준 사이를 잇지 않음**: 그룹 1,508개가 모두 기준 하나씩만 가지고 있어 한 줄 안의 묶음만 표시됩니다. 3차 회의 A6 사례(`NCT06110130-I03` "... OR" + `I04`)처럼 **여러 줄로 나뉜 선택지는 연결되지 않습니다.** 같은 `group_id`를 여러 기준에 붙여 주세요. 후보: 원문이 "or"로 끝나는 6줄(`NCT06110130-I03`, `NCT07594145-I01`·`I02`, `NCT06412198-E15`, `NCT07268131-E06`·`E07`)과 "Meets one of the following" 아래 줄들
3. **`lab_other`에 검사가 아닌 측정값** (mmHg, cm, mm, mL/m2 단위 7줄: `NCT07147114-I05`·`E07`, `NCT07254455-I05`·`E01`, `NCT07403058-E06`·`E11` 등): 측정 개념 키나 `term`을 붙여 주세요 (사소)
4. `concepts.json`에 코드가 없는 개념이 많음 (점수·바구니 키는 괜찮음). LOINC 49개의 공식 이름 대조(`--online`)는 합성 담당이 맡겠습니다

## 4. 행정 항목 후보 205줄 (`admin_candidates.csv`)

정답이 있는 기준 중 후보에 든 것은 10줄입니다. 합성 담당 판단:

| 기준 | 판단 | 시험 판정 영향 |
| --- | --- | --- |
| `NCT06848166-I01` 정보 설명서 읽고 서명 | 행정 항목 맞음 | 없음 (이미 ineligible) |
| `NCT07018323-I04` "Other, more specific inclusion criteria are defined in the protocol", `E04` 같은 문구 | 판정할 수 없는 자리표시 문장이라 행정 항목으로 보는 게 맞음 | **SYN-0020 × NCT07018323이 potential → eligible로 바뀜**. 팀 확인 후 반영 (`criteria_complete: false`라 브리핑에는 "공개되지 않은 기준 있음" 표시) |
| `NCT03424005-I01` "must meet all of the following ..." 머리줄 | 기준이 아니라 제목 줄. 행정 항목으로 처리 | 없음 |
| `NCT03424005-I10` "Adequate hematologic ... defined by the following" | 제목 줄이지만 아래 수치 기준의 묶음이라 행정 항목 아님 | 없음 |
| 연구자 판단·다른 임상시험 참여 제외 기준 5줄 | 행정 항목으로 하지 않음 (6.3 판단 표현 규칙 적용, 제외 MISSING은 판정을 막지 않음) | 없음 |

나머지 195줄(정답 대상이 아닌 시험)은 반영해도 정답에 영향이 없으니 CT.gov 담당 판단대로 하시면 됩니다.

## 5. 다음

- test 7,029줄: 같은 스크립트로 진행해 주세요. 받으면 같은 검사를 돌립니다
- 합성 담당: 정답 근거 채우기 → v4 묶음, 변형 대상 선정 (`time_window.max_days_before` + 정답 PASS → expired, `exists`/`not_exists` → conflict·unsupported)

## 6. LOINC 공식 이름 대조 (2026-10-09, `check_concepts.py --online`)

concepts.json의 LOINC 코드 51개를 NLM 공개 서비스로 조회했습니다. **모두 우리 개념과 같은 검사**를 가리킵니다 (틀린 코드 0). 결과 전체: `ctgov_v2/dev/check_online.txt`.

- 참고: `spo2`(59408-5)는 "맥박 산소측정" 코드라 기록의 SpO2와 맞습니다. `egfr`(62238-1)는 CKD-EPI 공식 기준이라 합성 기록과 맞습니다.
- 코드가 없는 개념(점수·바구니 키 등)은 그대로 둬도 됩니다. 필요해지면 추가합니다.

## 7. dev v2(final) / test v1 확인 — 2026-10-22

`stage2/check_concepts.py --ref-criteria ctgov_v1/criteria.jsonl`로 확인했다. 보고서는 `ctgov_v2/{dev,test}/check_report.txt`.

| 확인 | dev v2 | test v1 |
| --- | --- | --- |
| 기준 ID·원문 | 3,856행, 빠짐·추가·원문 변경 0 | 7,029행, 빠짐·추가·원문 변경 0 |
| `administrative` 빈 값 | 0 (true 292 / false 3,564) | 0 (true 558 / false 6,471) |
| `logic_group` | 여러 줄 선택지 묶음 8개 / 28행, 한 줄짜리는 `inline_relation`으로 | 묶음 11개 / 39행 |
| 단위 오류 | 요청한 2건 수정 (`migraine_attack_frequency` 새 개념, UACR mg/g). 오류 0 | 오류 28건 (아래) |
| 개념 사전 | 138개, dev·test 같은 파일 | |

dev는 5장에서 요청한 세 가지가 모두 반영되어 확정.

test 단위 오류 28건:

- 같은 단위를 다르게 쓴 것 (개념 사전 `alt_units` 추가로 해결, 21건): `cells/mm3`·`cells/mm^3`·`mm^3`(CD4, 6), `year`(기대 여명, ×12, 5), `E9/L`·`G/L`(10^9/L, 2), `pounds`, `cps/mL`, `cc/min`, `µM` 크레아티닌(÷88.4), `pmol/mL` C-peptide(×3.02), `mg`·`g` 24시간 단백뇨(2)
- 크레아티닌 청소율이 `mL/min/1.73m2`(3)이고 eGFR이 `ml/min/m^2`(1): 체표면적 보정 단위로 같게 봄 (×1)
- 원문 오타로 보이는 것: 혈소판 `100,000 mL`(→ /µL, 100 ×10^9/L), 알부민 `2.5 mg/dL`(→ g/dL, UACR과 같은 처리)
- HBV DNA `copies/mL` vs `IU/mL`: 환산이 근사값(약 5.8 copies = 1 IU)이라 단위 그대로 두고 판정 때 환산
- 칼륨 "within normal limit"이 `between` 값 없음: 수치 기준이 아니라 기록의 참고 범위로 판정할 기준이라 `free_text`로 두거나 값 없이 참고 범위 판정으로 처리

이 중 test 정답 쌍에 걸린 기준은 11개(PASS 5, UNKNOWN 6)라 test 정답 근거 채우기 전에 정리한다.

**처리 (2026-10-22, 합성 담당 쪽에서):** CT.gov 쪽 수정은 여기까지라 test 단위 28건은 `stage2/fix_ctgov_units.py`로 우리가 정리했다. 개념 사전에 같은 단위 표기와 표준 환산 24개를 `alt_units`로 추가했다(dev·test 같은 사전). test 기준 5행은 고치고 `fix_note`를 남겼다(CD4 단위 표기, 혈소판·알부민 원문 오타, eGFR 단위, 칼륨 "정상 범위 이내"는 `free_text`로). 원본은 `concepts.orig.json`, `criteria.orig.jsonl`로 보관했다. 다시 확인한 결과 dev·test 모두 오류 0이다.

**dev·test 공통 시험 (2026-10-22 추가):** 시험 4개(NCT06172478, NCT06582017, NCT06586957, NCT07254455)는 dev와 test 양쪽 후보에 있어 CT.gov가 두 번 파싱했고 54행이 달랐다. 원인은 handoff가 test 판으로 덮어쓰는데 `ctgov_v2/dev/criteria.jsonl`·`for_agent2_1022.zip`은 dev 판이었던 것. test v1 판이 더 새것이라(치료 차수 단위 `lines`, 방사선 치료 `procedure`, 빠진 구조화 2행 등) 이 판으로 통일했다 (`fix_ctgov_units.py` 3번, 원본 `criteria.orig.jsonl`). dev 정답 쌍은 NCT06582017 1쌍만 걸리고 정답 판정·근거는 그대로. **CT.gov 원본(dev v2)도 이 4개 시험은 test v1 행으로 바꿔 달라고 요청.**

## 8. 행정 항목 기준 (2026-10-25, 4차 회의 안건 3)

동의서 서명·의향·앞으로의 피임 동의는 `administrative: true`, 조직·검체 보유·현재 피임 방법·임신·수유처럼 기록으로 답할 수 있는 것은 `false`. 우리 사본에서 dev 5행(에이전트 3 담당 제안), test 14행(에이전트 3 v3 후보 71행을 같은 기준으로 분류)을 `false`로 바꿈. 목록: `admin_false_1025.csv`. 에이전트 1(CT.gov) 원본에는 아직 미반영이며, 담당에게 알림만 함(원본 수정 요청 아님). `admin_false_1025.csv`는 노션에 올려 공유함 (2026-10-27 확인).
