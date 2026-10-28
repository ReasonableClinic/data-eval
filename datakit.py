#!/usr/bin/env python3
"""Index and launcher for the synthetic data / gold / eval tools in this folder.

  python3 datakit.py                  list the commands by group
  python3 datakit.py <command> [...]  run that tool; extra arguments go to it unchanged
  python3 datakit.py selfcheck        format checks on the final patients and variant sets (no API calls)

The tools stay where they are (nothing moved, nothing renamed). Each one runs from the folder its own usage line
assumes, shown as "cwd" in the list, so paths in its arguments are relative to that folder, as before.
"""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# (group, command, script, cwd, description, example arguments)
COMMANDS = [
    ("생성 (기록용, 다시 돌릴 일 없음)", "gen-build", "generation/build.py", ".", "손으로 쓴 기본 기록 → 환자 파일", ""),
    ("생성 (기록용, 다시 돌릴 일 없음)", "gen-generate", "generation/generate_patients.py", ".", "LLM으로 환자 기록 생성", "--help"),
    ("생성 (기록용, 다시 돌릴 일 없음)", "gen-enrich", "generation/enrich_patients.py", ".", "종합 진료기록·최근 검사 추가", "--help"),

    ("형식 검사", "validate", "validate.py", ".", "② 환자 기록 형식 검사", "patients_v2.jsonl"),
    ("형식 검사", "check-concepts", "stage2/check_concepts.py", "stage2", "개념 사전·①-b 필드 검사",
     "--concepts ../ctgov_v2/dev/concepts.json --criteria ../ctgov_v2/dev/criteria.jsonl --ref-criteria ../ctgov_v1/criteria.jsonl"),

    ("CT.gov (①)", "ctgov-convert", "stage2/ctgov_to_common.py", "stage2", "CT.gov API 응답 → ⓪·①-a (참고용 변환기)", "--help"),
    ("CT.gov (①)", "ctgov-fix-units", "stage2/fix_ctgov_units.py", "stage2", "①-b 단위 보정, 행정 항목 false 지정", ""),
    ("CT.gov (①)", "classify-admin", "stage2/classify_admin.py", "stage2", "행정 기준 표시 (administrative)", "--help"),

    ("정답 (④)", "gold-label", "stage2/label_gold.py", "stage2", "LLM 1차 정답 초안 + 검수표", "--help"),
    ("정답 (④)", "gold-adjudicate", "stage2/adjudicate.py", "stage2", "검수 대상 기준에 3번째 의견", "--help"),
    ("정답 (④)", "gold-review-bundle", "stage2/make_review_bundle.py", "stage2", "검수 화면용 묶음 (한국어 설명)", "--help"),
    ("정답 (④)", "gold-apply-review", "stage2/apply_review.py", "stage2", "검수한 review.csv → gold", "--help"),
    ("정답 (④)", "gold-fill-evidence", "stage2/fill_gold_evidence.py", "stage2", "정답 근거에 개념·값·단위 채우기", "--help"),
    ("정답 (④)", "gold-audit-patch", "stage2/audit_patch.py", "stage2", "놓친 사실 점검 → review.csv 사본", "--help"),
    ("정답 (④)", "gold-apply-audit", "stage2/apply_audit_gold.py", "stage2", "점검 등급을 gold에 바로 반영", "--help"),
    ("정답 (④)", "gold-apply-fixes", "stage2/apply_gold_fixes.py", "stage2", "gold_fixes CSV로 정답 수정 (새 run 폴더)",
     "--run-in runs/dev_v10 --run-out runs/dev_v11 --fixes runs/gold_fixes_dev_MMDD.csv --date 2026-MM-DD --patients ../patients_v2.jsonl"),

    ("변형 세트 (공통 형식 7장)", "var-select", "stage2/variants/select_targets.py", "stage2/variants", "1단계 변형 대상 기준 고르기", "--split dev --out plan_dev.json"),
    ("변형 세트 (공통 형식 7장)", "var-edits-dev", "stage2/variants/make_edits_dev.py", "stage2/variants", "dev 기록 수정안 작성 → edits_dev.json", ""),
    ("변형 세트 (공통 형식 7장)", "var-edits-test", "stage2/variants/make_edits_test.py", "stage2/variants", "test 기록 수정안 작성 → edits_test.json", ""),
    ("변형 세트 (공통 형식 7장)", "var-build", "stage2/variants/build_variants.py", "stage2/variants", "2단계 변형 환자·정답 만들기", "--split dev --edits edits_dev.json --out-dir out_dev"),
    ("변형 세트 (공통 형식 7장)", "var-check", "stage2/variants/check_variants.py", "stage2/variants", "구조 검사 (문서 1개만 변경, span, 문서 순서)", "--split dev --dir out_dev"),
    ("변형 세트 (공통 형식 7장)", "var-verify", "stage2/variants/verify_variants.py", "stage2/variants", "3단계 LLM 블라인드 확인", "--help"),
    ("변형 세트 (공통 형식 7장)", "var-review", "stage2/variants/make_variant_review.py", "stage2/variants", "불일치 변형 검수 화면", "--split dev --dir out_dev"),
    ("변형 세트 (공통 형식 7장)", "var-finalize", "stage2/variants/finalize_variants.py", "stage2/variants", "4단계 final_<split>/로 고정", "--split dev --dir out_dev"),

    ("인계", "handoff", "make_handoff.py", ".", "dev·test·에이전트 3 zip 다시 만들기 (handoff/)", ""),
    ("인계", "kit-agent456", "stage2/agent456/make_agent456_kit.py", ".", "에이전트 4·5·6 개발 키트", ""),

    ("채점", "eval-variants", "stage2/agent456/eval_variants.py", ".", "기준 판정·순위 채점 (키트 안에서 쓰는 형태)", "--help"),
    ("채점", "eval-trec", "stage2/trec_eval/compare_trec.py", "stage2/trec_eval", "TREC 2021과 시험 단위 비교", "--help"),
    ("채점", "eval-trialgpt", "stage2/trec_eval/trialgpt/trialgpt_eval.py", "stage2/trec_eval/trialgpt", "TrialGPT 의사 주석과 기준 단위 비교", "--help"),
]

SELFCHECK = [
    ("validate.py", ".", ["patients_v2.jsonl"]),
    ("validate.py", ".", ["patients_eval_v2.jsonl"]),
    ("stage2/variants/check_variants.py", "stage2/variants", ["--split", "dev", "--dir", "out_dev"]),
    ("stage2/variants/check_variants.py", "stage2/variants", ["--split", "test", "--dir", "out_test"]),
]


def show():
    print(__doc__.split("\n\n")[0])
    group = None
    for g, name, script, cwd, desc, ex in COMMANDS:
        if g != group:
            print(f"\n[{g}]")
            group = g
        print(f"  {name:<20} {desc}")
        print(f"  {'':<20} {script}  (cwd {cwd})" + (f"\n  {'':<20} 예: python3 datakit.py {name} {ex}" if ex else ""))
    print("\n  selfcheck            최종 환자·변형 세트 형식 검사 한 번에 (API 호출 없음)")


def run(script, cwd, args):
    path = os.path.join(ROOT, script)
    return subprocess.call([sys.executable, path] + list(args), cwd=os.path.join(ROOT, cwd))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("list", "-h", "--help"):
        show()
        return 0
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "selfcheck":
        bad = 0
        for script, cwd, a in SELFCHECK:
            print(f"$ (cd {cwd}) python3 {os.path.basename(script)} {' '.join(a)}", flush=True)
            bad += run(script, cwd, a) != 0
        print("selfcheck:", "OK" if not bad else f"{bad} failed")
        return 1 if bad else 0
    hit = next((c for c in COMMANDS if c[1] == cmd), None)
    if not hit:
        print(f"unknown command {cmd!r}; python3 datakit.py list")
        return 2
    _, _, script, cwd, _, _ = hit
    print(f"(cwd {cwd}: 경로 인자는 이 폴더 기준)", file=sys.stderr, flush=True)
    return run(script, cwd, args)


if __name__ == "__main__":
    sys.exit(main())
