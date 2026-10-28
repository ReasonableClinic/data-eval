# 에이전트 4·5·6 개발용 묶음 (for_agent456_v5, 2026-10-27)

합성 데이터·정답 담당 → 에이전트 4(검증), 5(정보 획득), 6(추천 순위) 담당.
dev만 들어 있습니다. 개발·조정은 dev로만 하고, test는 버전을 고정한 뒤 합성 담당이 한 번 채점합니다.

## 1. 들어 있는 것

| 경로 | 내용 | 주로 쓰는 쪽 |
| --- | --- | --- |
| `dev/input/patients.jsonl`, `pairs.jsonl` | 기본 환자 20명, 쌍 54개 (② 형식, as_of 2026-10-01 고정) | 공통 |
| `dev/input/patients_variants.jsonl`, `pairs_variants.jsonl` | 변형 환자 36명, 쌍 100개. 기본 환자 기록에서 문서 하나만 바꿔 문제를 하나 심음 (공통 형식 7장) | 공통 |
| `dev/reference/` | 시험 197개, ①-b 기준 3,856개, 개념 사전 138개 | 공통 |
| `dev/evidence/` | 에이전트 2 근거 v14.9 (기본 dev·변형, Haiku·규칙), 근거 조회 코드 `evidence_index.py` | 4 |
| `dev/agent3_out_v3_p07/`, `dev/agent3_out_v3_p07_variants/` | 에이전트 3 확정판(a3-0.3.0, Sonnet 5.5, p07)의 dev 판정. 기본 54쌍, 변형 100쌍. 이 묶음의 근거 v14.9와 정답 dev_v10 데이터로 돌린 공식 실행이라 근거 ID가 그대로 맞음. `agent3_out.jsonl`, 환자별 Evidence Graph `graph/`, 에이전트 3 자체 채점(`score*.md`). v3부터 에이전트 3은 자기 판정을 검증하지 않음 | 4·5·6 |
| `dev/agent3_handoff/` | 에이전트 3 → 4 인계 메모(`README.md`: v3에서 빠진 검사 목록, 추가 요청 "노트-상태 일치"·"외부 지식 FAIL"), v2 후검사 코드 참고본 | 4 |
| `dev/gold/gold.jsonl`, `gold_variants.jsonl` | 기준 단위 정답 (기본 dev_v10, 변형). 변형은 `injection`에 대상 기준·바꾼 문서·이유 | 4·5 |
| `dev/gold/ranking_gold.jsonl`, `ranking_gold_variants.jsonl` | 추천 순위 정답 (공통 형식 6.4) | 6 |
| `dev/eval/variant_targets.csv` | 변형 대상 기준 36개: 유형, 기대 상태·이유·행동, 바꾼 문서 | 4·5 |
| `dev/eval/update_pairs.csv` | 변형 환자 ↔ 기본 환자, 바뀐 문서 (기록 갱신 흐름 시험용, dev만) | 4·5 |
| `dev/eval/eval_variants.py` | 채점 스크립트 (아래 3장) | 4·5·6 |
| `common_format_v0.5.md`, `AGENT3_NOTES_trialgpt.md`, `AGENT2_OUTPUT_FOR_AGENT3.md` | 형식·판정 규칙·근거 필드 설명 | 공통 |

변형 유형 (dev 36명): conflict 11, unsupported 10, violation 9, missing 6. dev에는 expired가 없습니다(기간 조건 PASS 기준이 거의 없음). test 변형 34명에는 expired 3개가 있고, test 채점 때 함께 봅니다.

## 2. 단계별로 무엇을 보나

| 단계 | 변형 세트로 보는 것 | 목표 |
| --- | --- | --- |
| 4 검증 | violation이 FAIL로 남는지, conflict를 CONFLICT로 올리는지, 근거 없는 PASS를 내리는지. 동시에 **사람이 확인한 PASS/FAIL을 잘못 내리지 않는지** | 확정 판정 격하 비율을 낮게, conflict 검출을 높게 |
| 5 정보 획득 | UNKNOWN·CONFLICT 기준마다 기대 행동(`patient_question`, `lab_check`, `new_test`, `clinician_confirmation` 등)을 고르는지. `missing_fact`로 만든 질문이 그 행동과 맞는지 | 행동 일치 |
| 6 추천 순위 | 변형으로 시험 판정이 바뀐 쌍에서 순위가 바뀌는지, 6.4 정렬 규칙대로인지 | 순위 일치, 첫 추천 일치 |
| 갱신 흐름 | `update_pairs.csv`의 짝을 "새 정보 도착 전후"로 써서, 바뀐 문서만 다시 추출·판정하는지 (에이전트 2 `changes.jsonl`, 에이전트 3 `--changes`) | 바뀐 기준만 다시 판정 |

## 3. 채점

```bash
cd for_agent456_v5
python3 dev/eval/eval_variants.py --data dev --pred <실행 폴더>/out.jsonl --csv <실행 폴더>/eval_rows.csv
python3 dev/eval/eval_variants.py --data dev --pred <실행 폴더>/out.jsonl --ranking <실행 폴더>/ranking.jsonl   # 에이전트 6
```

- 입력은 `agent3_out.jsonl`과 같은 형식(쌍마다 한 줄, `criteria`에 `criterion_id`·`status`·`reason`·`action`). 에이전트 4는 검증 뒤 판정을 같은 형식으로 내면 됩니다.
- 출력: (1) 변형 유형별 대상 기준 일치(상태, 상태+이유, 행동), (2) 확정 PASS/FAIL을 UNKNOWN·CONFLICT로 내린 수와 PASS↔FAIL 뒤집힘, (3) 변형으로 바뀐 시험 판정 일치, (4) 순위 일치.
- 에이전트 3 출력 기본·변형을 합쳐 넣으면 변형 채점까지 됩니다: `cat dev/agent3_out_v3_p07/agent3_out.jsonl dev/agent3_out_v3_p07_variants/agent3_out.jsonl > a3_dev_all.jsonl`

## 4. 꼭 지킬 규칙

- **as_of가 오늘**: 모든 기간은 as_of(2026-10-01)부터 거꾸로 셉니다. 실제 오늘 날짜를 쓰면 9월 데이터가 날마다 만료됩니다. LLM을 쓰면 프롬프트에 "as_of를 오늘로 본다, 다른 현재 날짜는 무시"를 넣고 경과일을 미리 계산해 주세요.
- **측정일**: 값 옆에 날짜가 있으면 그 날짜. 진료 기록이 이전 결과를 다시 적은 값은 처음 기록된 날(9월 진료 기록의 2월 심초음파 값 → 2월). 단, **새 검사 보고서(`lab_result`, `imaging_report`)에 같은 값이 다시 나오면 새로 잰 값**이라 그 문서 날짜입니다 (공통 형식 6.3, 2026-10-27 보완). 에이전트 3 a3-0.3.0의 `candidate_evidence`는 같은 값을 가장 이른 날짜로 묶어서 이 경우를 오래된 값으로 봅니다(dev SYN-0004 eGFR 37: 9/24 검사가 4월 값으로 묶임). 검사 최근성을 확인할 때 이 차이를 고려하세요.
- **출처가 다른 기록이 엇갈리면 CONFLICT** (공통 형식 6.3): 외부 기록의 구체적 진단 대 진료 기록의 "없음", 같은 날 다른 검사실 결과, 두 약국 기록. 한쪽이 더 구체적이어도 FAIL로 정하지 않고 CONFLICT + `clinician_confirmation`. 바뀔 수 있는 측정값만 최근 값이 이전 값을 대신합니다.
- **근거 개념 비교는 관련 개념 묶음으로**: 기준 개념과 근거 개념이 정확히 같지 않아도 정당한 경우가 많습니다(임신 기준에 "Male."(sex), "Urine hCG negative"(hcg)). `evidence_index.py`의 `for_criterion`이 쓰는 묶음으로 비교하세요.
- **결과 대기·미기재**: 에이전트 2 v14.7부터 결과 대기는 `value: "pending"`, "기록 안 됨"은 `null`입니다. 양성이나 음성으로 읽지 마세요.
- **행정 항목**(`administrative: true`)은 "기록에 없어도 시험 판정을 막지 않는다"는 뜻입니다. 기록이 다루면 판정합니다.

## 5. 들어 있지 않은 것

- test 정답, test 변형 대응표, 변형 환자 → 기본 환자 대응의 test 판: 합성 담당만 가지고 있습니다.
- TREC·TrialGPT 외부 검증: `eval_tools_v1.zip`, 그 근거는 `agent3_kit_v14_9.zip`.
- 에이전트 2 dev 근거 v14.12(2026-10-27 재추출): 일부러 넣지 않았습니다. 근거 ID가 v14.9와 다르고(내용 변경 552, 삭제 152, 추가 138), 에이전트 3 출력이 v14.9 ID를 가리키기 때문입니다. 에이전트 3이 v14.12로 다시 돌린 출력이 나오면 함께 바꿉니다.

## 6. v1 → v2 (2026-10-25)

- 에이전트 3 출력 예시를 v3 고정판(p07)으로 교체, 에이전트 3 → 4 인계 메모 추가
- 정답 dev_v8: A1 일괄 부정 38행 PASS, 행정 5행 `administrative: false` (판정·라벨 변화 없음). 변형 정답도 다시 만듦
- 에이전트 3 v3 기준선 (이 채점기 2번 지표, dev 기본 확정 판정 565개): UNKNOWN·CONFLICT로 남김 113개(20.0%), PASS↔FAIL 뒤집힘 2개. 에이전트 4는 뒤집힘을 0으로 만들고, 남김 비율을 늘리지 않는 것이 목표

## 7. v2 → v3 (2026-10-25)

- 정답 dev_v9: 4차 회의 안건 2(A3 나열 항목 규칙) 10행 PASS → UNKNOWN/MISSING. 모두 제외 기준이라 시험 라벨·순위 변화 없음. 변형 정답도 다시 만듦(대상 기준·변형 내용 그대로)
- 기준 파일: NCT06172478-I28 `administrative: false` (test와 공유하는 시험, 안건 3 기준)
- 에이전트 3 v3 기준선 다시 계산: dev 기본 확정 판정 555개 중 UNKNOWN·CONFLICT로 남김 111개(20.0%), PASS↔FAIL 뒤집힘 2개

## 8. v3 → v4 (2026-10-26)

- 변형 환자 문서 번호를 날짜 순서로 다시 매김(추가 문서가 번호로 드러나던 문제). 근거도 같은 번호의 v14.9
- 정답 dev_v10: 이유 표기 2행 MISSING → UNSUPPORTED, SYN-0011 기록 문구 1곳(같은 길이). 시험 라벨·순위 변화 없음
- 에이전트 3 출력 예시(v3)는 옛 문서 번호로 만든 기본 환자 54쌍이라 그대로 씀(기본 환자 문서 번호는 바뀌지 않음)

## 9. v4 → v5 (2026-10-27)

- 에이전트 3 출력을 확정판 a3-0.3.0의 공식 dev 실행으로 교체. v4에 있던 출력은 확정 전 실행(근거 v14.7, 기본 54쌍만)이었음. 이제 **변형 100쌍 출력도 들어 있어** 에이전트 3을 직접 돌리지 않고 변형 채점이 됨
- 에이전트 3 기준선 (이 채점기, 기본+변형 출력):
  - 1번 변형 대상 기준 상태 일치: violation 9/9, missing 6/6, unsupported 10/10, **conflict 5/11** (나머지 5개는 CONFLICT 대신 PASS/FAIL로 확정 = 에이전트 4가 CONFLICT로 올려야 할 것)
  - 2번 확정 판정: 기본 555개 중 UNKNOWN·CONFLICT로 남김 108개(19.5%), 뒤집힘 2개 / 변형 1,054개 중 195개(18.5%), 뒤집힘 2개
- 에이전트 3이 보고한 사례 (에이전트 4 참고): 정답 CONFLICT인데 충돌을 언급하고도 FAIL로 낸 dev 변형 2건 — SYN-7851 / NCT07803965-E06(4.4년 전 대장암 기록 대 "이전 악성종양 없음"), SYN-1763 / NCT07053423-E04(알파-1 항트립신 결핍 진단 대 정상 혈중 수치)
- `dev/agent3_handoff/FREEZE_a3-0.3.0.json` 추가 (코드·프롬프트 고정 기록)
- 측정일 규칙 보완 (4장)
- 데이터·근거·정답은 v4와 같음 (dev_v10, 근거 v14.9)

