# CT.gov 담당 요청: 질환별 임상시험 수집

합성 환자 50명(dev 20, test 30)에 대조할 임상시험이 필요합니다. 질환 목록은 `conditions_for_ctgov.csv`(엑셀용)와 `conditions_for_ctgov.json`(코드용)에 있습니다.

## 검색 방법

- 엔드포인트: `https://clinicaltrials.gov/api/v2/studies`
- 파라미터:
  - `query.cond` = 목록의 `query_cond`
  - `query.term` = 목록의 `query_term` (비어 있으면 생략)
  - `filter.overallStatus` = `RECRUITING,NOT_YET_RECRUITING`
  - `filter.advanced` = `AREA[StudyType]INTERVENTIONAL` (관찰연구 제외. E001 검색에서 동작 확인)
  - `pageSize` = 20
- 예: `https://clinicaltrials.gov/api/v2/studies?query.cond=gastric+cancer&query.term=HER2-positive&filter.overallStatus=RECRUITING,NOT_YET_RECRUITING&filter.advanced=AREA[StudyType]INTERVENTIONAL&pageSize=20`
- 아래 코드 필터를 거친 뒤 남은 시험이 `trials_wanted`보다 적으면 `nextPageToken`으로 다음 페이지를 받습니다. 그래도 적으면 `query_term`을 빼고 다시 검색합니다.

## 코드에서 거를 것 (API 필터로 안 걸러짐)

1. `designModule.designInfo.primaryPurpose`가 `TREATMENT`가 아닌 시험은 뒤로 미룹니다. `DIAGNOSTIC`, `SCREENING`(영상·검사 연구)은 제외합니다. `query.term`은 정확히 일치하는 검색이 아니라서 HER2 영상 진단 연구 같은 것이 섞여 나옵니다.
2. `statusModule.statusVerifiedDate`가 12개월 넘게 지난 시험(지금 기준 2025-10 이전)은 상태가 실제와 다를 수 있으니 뒤로 미룹니다. 다른 후보가 없을 때만 쓰고, ⓪ `status_verified`에 그대로 남깁니다.
3. 국가는 시험 전체 상태가 아니라 기관별 `locations[].status`로 판단합니다. `RECRUITING`·`NOT_YET_RECRUITING`인 기관의 국가만 ⓪ `countries`에 넣습니다.
4. 기준 원문은 `eligibilityModule.eligibilityCriteria`만 씁니다. `detailedDescription`에 같은 기준이 다시 적혀 있어도 무시합니다.

## 고르는 규칙

- 질환당 시험 3개(`trials_wanted`). 위 필터를 통과한 치료 목적 중재 연구에서 고릅니다.
- 환자의 나이·성별이 시험의 `minimumAge`~`maximumAge`, `sex` 안에 들어가는 시험만 고릅니다. 소아(`age_group`이 child/infant)는 소아를 받는 시험이어야 합니다.
- 나이·성별 외의 기준으로는 거르지 않습니다. 환자가 다른 기준에서 FAIL이 나는 시험도 정답 데이터에 필요합니다. (예: E001은 이미 1차 치료 중인데, 1차 치료 전 환자만 받는 시험도 FAIL 사례로 쓸 수 있음)
- 후보가 많으면 한국 기관이 모집 중인 시험을 하나 이상 넣어 주세요. 추천 순위 정답에 필요합니다.
- 조건에 맞는 시험이 없으면 비워 두고 아래 `trial_candidates.jsonl`에 `"n_found": 0`으로 남깁니다. `note`에 "시험이 거의 없을 수 있음"이라고 적힌 질환은 예상된 일이니 억지로 채우지 않습니다.

## 돌려받을 파일 (공통 형식)

| 파일 | 내용 | 필수 |
| --- | --- | --- |
| `trials.jsonl` | ⓪ Trial v0.4 (원문 `eligibility_text`, `fetched_at`, `status_verified`, `study_type`, `primary_purpose`, `sites`, `criteria_complete` 포함. 나이는 연 단위 소수, 연락처 제외) | O |
| `criteria.jsonl` | ①-a 분할 (`trial_id`, `criterion_id`, `type`, `original_text`, `cohort`, `parse_status`). 번호는 순서대로 다시 매기고 `\>`·`\<` 이스케이프와 위 첨자를 정리 | O |
| `criteria.jsonl`의 ①-b | 최소한 `time_window`. 나머지 필드는 나중에 채워도 됨 | 가능하면 |
| `trial_candidates.jsonl` | 한 줄에 `{"base_id", "trial_ids": [...], "query_cond", "query_term", "n_found"}` | O |

같은 시험이 여러 질환에 걸리면 `trials.jsonl`에는 한 번만 넣고, `trial_candidates.jsonl`에서 여러 `base_id`가 같은 `trial_id`를 가리키게 하면 됩니다.

자세한 필드 정의는 공통 형식의 ⓪·① 절을 따릅니다.

변환 참고 코드 `ctgov_to_common.py`와 실제 응답으로 만든 예시(`example/`)를 같이 넣었습니다. 그대로 써도 되고, 규칙만 참고해도 됩니다.
