# 합성 데이터 2단계: 정답(④) 달기

환자(②)와 CT.gov 담당이 고른 시험(⓪·①-a)을 짝지어 정답 `gold.jsonl`을 만듭니다. 형식과 판정 규칙은 `../docs/common_format_v0.5.md` 6장을 따릅니다.

```
⓪ trials + ①-a criteria (+ classify_admin.py로 행정 항목 표시) + ② patients + trial_candidates
 └─ label_gold.py ─────────▶ gold_draft.jsonl, gold_draft.run2.jsonl, review.csv   (LLM 두 번 판정)
     └─ adjudicate.py ─────▶ adjudication.jsonl                                     (심판 LLM, 확인 기준만)
         └─ make_review_bundle.py ─▶ review_bundle.json                             (한국어 번역 포함)
             └─ 정답 검수실 (웹 화면)에서 검수 ─▶ review.csv 내보내기
                 └─ apply_review.py --accept-agreed ─▶ gold.jsonl, ranking_gold.jsonl, gold_review_log.jsonl
```

## 결과 (`runs/`)

| 폴더 | 환자 | 쌍 | 상태 |
| --- | --- | --- | --- |
| `runs/dev_v3` | dev 20명 (`../patients_v2.jsonl`) | 54 | 검수 완료, 모두 human_verified |
| `runs/test_v3` | test 30명 (`../patients_eval_v2.jsonl`) | 90 | 검수 완료, 모두 human_verified |

각 폴더: `gold_draft*.jsonl`(1·2차 판정), `gold_draft_notes*.jsonl`(설명·토큰), `run_agreement.json`(1·2차 일치율), `adjudication.jsonl`(심판), `review_bundle.json`(검수 화면용), `review.csv`(검수 결과), `gold.jsonl`·`ranking_gold.jsonl`(최종 정답), `gold_review_log.jsonl`(바꾼 내역), `progress.log`.

## 파일

| 파일 | 내용 |
| --- | --- |
| `label_gold.py` | LLM 판정 두 번(temperature 0, 0.7). 이어서 실행 가능(끝난 판정은 건너뜀). `--only E030`으로 일부만 |
| `prompt_label_gold.md` | 판정 규칙 프롬프트 |
| `adjudicate.py` | 확인 표시 기준과 시험 판정이 갈린 쌍을 심판 LLM이 다시 판정하고 한국어로 해설. 이어서 실행 가능 |
| `make_review_bundle.py` | 검수 화면용 `review_bundle.json` 생성. 한국어 번역은 `ko_cache.json`에 저장해 재사용 |
| `apply_review.py` | 검수한 `review.csv`로 최종 정답 생성. `--accept-agreed`: 1·2차가 일치해 화면에 나오지 않은 기준은 인정 |
| `classify_admin.py` | 기준마다 행정 항목(동의서·순응 등) 여부를 한 번 표시 → `criteria.jsonl`의 `administrative` |
| `ctgov_to_common.py` | CT.gov API 응답 → ⓪·①-a 변환 (분할 규칙 수정본) |
| `gold_lib.py` | 공통 함수 (근거 위치 찾기, 판정 검사, 시험 단위 판정, 순위, LLM 호출) |
| `check_concepts.py` | ①-b가 오면: concepts.json 검사(키·코드 형식·검증 숫자·단위), ①-b 필드 검사, 기준 ID가 정답에 쓴 파일과 같은지 확인. `--online`은 NLM 공개 서비스에서 공식 이름 조회 |
| `fill_gold_evidence.py` | ①-b가 오면: 정답 근거의 `concept`·`value`·`unit`을 LLM으로 채우고 검사. 답은 `evidence_concepts.jsonl`에 저장해 다시 돌려도 새로 묻지 않음 |
| `trec_eval/` | 라벨러 TREC 검증 (시험 단위, `trec_eval/README.md`) |
| `ko_cache.json` | 번역 캐시 |
| `fixtures/` | 프롬프트·스크립트 시험용 (`dev_demo`는 가상 시험, 제출 데이터에 섞지 않음) |

## 실행 (stage2 폴더에서)

API 키: OpenRouter는 `OPENROUTER_API_KEY`, Claude는 `ANTHROPIC_API_KEY`. 명령에 `#` 주석이나 `!`를 넣지 마세요 (zsh 오류).

1. LLM 판정 (test 예시)

```
python3 label_gold.py --trials ../ctgov_v1/trials.jsonl --criteria ../ctgov_v1/criteria.jsonl --patients ../patients_eval_v2.jsonl --id-map ../id_map_eval.json --candidates ../ctgov_v1/trial_candidates.jsonl --provider openrouter --model openai/gpt-oss-120b --out runs/test_v3/gold_draft.jsonl
```

dev는 `--patients ../patients_v2.jsonl --id-map ../id_map.json --out runs/dev_v3/gold_draft.jsonl`. 기준이 아주 많은 시험에서 시간 초과가 나면 앞에 `LLM_DEADLINE=600 `을 붙여 그 환자만 `--only`로 다시 돌립니다.

2. 심판

```
python3 adjudicate.py --run runs/test_v3 --patients ../patients_eval_v2.jsonl --trials ../ctgov_v1/trials.jsonl --provider anthropic --model claude-sonnet-5-5
```

3. 검수 화면 파일

```
python3 make_review_bundle.py --run runs/test_v3 --patients ../patients_eval_v2.jsonl --trials ../ctgov_v1/trials.jsonl --provider openrouter --model openai/gpt-oss-120b
```

`runs/test_v3/review_bundle.json`을 정답 검수실(웹 화면)에 열어 검수하고, `review.csv`로 내보내 같은 폴더에 저장합니다. 이전에 내보낸 `review.csv`를 함께 열면 이어서 검수할 수 있습니다.

4. 최종 정답

```
python3 apply_review.py --accept-agreed --draft runs/test_v3/gold_draft.jsonl --review runs/test_v3/review.csv --patients ../patients_eval_v2.jsonl --trials ../ctgov_v1/trials.jsonl --out runs/test_v3/gold.jsonl
```

`0 errors`이고 `still llm`이 0이면 끝입니다. "모르겠음(의료진 확인)" 표시가 남은 쌍은 `human_verified`가 되지 않습니다.

## ①-b가 오면 (CT.gov 담당의 새 criteria.jsonl과 concepts.json, 예: `../ctgov_v2/`)

1. 검사. 오류가 0이어야 다음 단계로 갑니다. 기준 ID가 바뀌었으면 CT.gov 담당과 먼저 맞춥니다.

```
python3 check_concepts.py --concepts ../ctgov_v2/concepts.json --criteria ../ctgov_v2/criteria.jsonl --ref-criteria ../ctgov_v1/criteria.jsonl
```

코드 이름 대조는 내 터미널에서 (인터넷 필요):

```
python3 check_concepts.py --concepts ../ctgov_v2/concepts.json --online
```

2. 정답 근거 채우기 (dev, test 각각). 먼저 `--dry-run`으로 프롬프트를 보고, 실행 후 `fill_report.csv`의 PROBLEM 줄과 값을 확인한 뒤 `--apply`.

```
python3 fill_gold_evidence.py --run runs/dev_v3 --patients ../patients_v2.jsonl --criteria ../ctgov_v2/criteria.jsonl --concepts ../ctgov_v2/concepts.json --provider openrouter --model openai/gpt-oss-120b
```
```
python3 fill_gold_evidence.py --run runs/dev_v3 --patients ../patients_v2.jsonl --criteria ../ctgov_v2/criteria.jsonl --concepts ../ctgov_v2/concepts.json --provider openrouter --model openai/gpt-oss-120b --apply
```

`apply_review.py`를 다시 돌리면 gold.jsonl이 새로 만들어지므로, 그 뒤에 `fill_gold_evidence.py --apply`를 다시 실행합니다 (저장된 답을 쓰므로 LLM 호출 없음). 마지막에 `python3 ../make_handoff.py`.

## 검수 화면 사용법 요약

- 단축키: `J`/`K` 이동, `1` 1차 동의, `2` 2차 채택, `3` 심판 채택, `P`/`F`/`U`/`C`/`N` 직접 판정, `M` 모르겠음, `/` 기록 찾기, `[` `]` 해당 기준 이동
- 필터: 판정 갈림, 의료진 확인, 보완 필요(다음 행동·근거 빠짐)
- 오른쪽 기록에서 문장을 드래그해 "선택한 문장을 근거로 추가"
- 상단 "용어집"에 의학 용어 해설

## 주의

- test 기록은 개발 중에 보지 않습니다. 프롬프트나 규칙은 dev로만 고칩니다.
- 기준 ID는 `../ctgov_v1/criteria.jsonl`에 묶여 있습니다. 기준을 다시 나누면 해당 쌍의 정답을 다시 달아야 합니다.
- `gold_evidence`의 `concept`, `value`, `unit`은 비어 있습니다. ①-b와 `concepts.json`이 정해지면 채웁니다.
