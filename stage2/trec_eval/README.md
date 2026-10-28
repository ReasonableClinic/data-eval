# 라벨러 TREC 검증 (제안 6번, 시험 단위)

우리 정답 라벨러(`label_gold.py`, gpt-oss-120b 두 번 판정)를 TREC 2021 공식 정답(qrels)과 비교합니다. 합성 세트 정답을 얼마나 믿을 수 있는지 보여 주는 근거입니다.

## 표본

TREC 담당의 `trec_parsing.zip`(공통 형식 변환본)에서 뽑았습니다 (seed 42).

| 파일 | 내용 |
| --- | --- |
| `qrels_sample.jsonl` | 정답 100쌍: eligible 50 + excluded(ineligible) 50. 환자 70명에 고르게 퍼지도록 추출. 기준이 0개인 시험은 제외 |
| `patients.jsonl` | TREC 환자 70명 (`as_of` 2021-04-27) |
| `trials.jsonl`, `criteria.jsonl` | 표본 시험 100개, 기준 1,072개 (2021년 버전) |
| `trial_candidates.jsonl`, `id_map_trec.json` | `label_gold.py` 입력 형식 맞춤용 (TREC는 환자 ID = 기본 ID) |
| `compare_trec.py` | 결과와 qrels 비교 |

TREC 환자는 생년월일 문서가 없어서, 나이·성별은 본문("45-year-old man", "74M", "55yo woman")에서 읽도록 `gold_lib.py`를 고쳤습니다 (합성 세트에는 영향 없음).

## 실행 (stage2/trec_eval 폴더에서)

1. 행정 항목 표시 (합성 세트와 같은 규칙으로 비교하기 위해)

```
python3 ../classify_admin.py --criteria criteria.jsonl --candidates trial_candidates.jsonl --provider openrouter --model openai/gpt-oss-120b
```

2. 라벨러 실행 (두 번 판정)

```
mkdir -p runs/trec_v1
```
```
python3 ../label_gold.py --trials trials.jsonl --criteria criteria.jsonl --patients patients.jsonl --id-map id_map_trec.json --candidates trial_candidates.jsonl --provider openrouter --model openai/gpt-oss-120b --out runs/trec_v1/gold_draft.jsonl
```

3. 비교

```
python3 compare_trec.py --run runs/trec_v1 --qrels qrels_sample.jsonl --criteria criteria.jsonl
```

## 결과 읽는 법

- TREC 정답은 eligible과 excluded 두 가지뿐입니다. 우리 라벨러의 `potential`(확인 필요)은 TREC에 없는 값이라 세 가지로 계산합니다.
  - `kappa_without_potential`: potential 쌍을 빼고 계산 (주 지표)
  - `kappa_potential_as_eligible`, `kappa_potential_as_ineligible`: potential을 한쪽으로 몰았을 때 (범위 확인용)
- 합격 기준 제안: 시험 단위 κ 0.6 이상 (공통 형식 10장)
- `qrels_ineligible_and_ours_ineligible_because`: TREC의 excluded는 "선정 기준은 맞지만 제외 기준에 걸림"이라는 뜻입니다. 우리 판정이 제외 기준 FAIL에서 나왔는지 봅니다.
- `trec_disagreements.csv`: 판정이 다른 쌍과 그 원인 기준. 회의 때 오류 유형을 볼 때 씁니다.
- 기준 단위 검증(TrialGPT 전문가 주석과 비교)은 주석 데이터를 구하면 따로 합니다.
