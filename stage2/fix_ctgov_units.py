#!/usr/bin/env python3
"""Our side fixes to CT.gov ①-b units (CT.gov said their files are final, 2026-10-22).

1. Adds alt_units to concepts.json (same dictionary for dev and test). Only spellings of the same unit and
   standard conversions; the meaning of a concept does not change.
2. Fixes 5 test criteria rows (units) and sets administrative false on 14 test rows (TEST_ADMIN_FALSE); each gets a `fix_note` saying what changed and why.
3. Trials that are in both dev and test (4 trials, 54 rows differ): CT.gov parsed them twice. One version for
   both splits: the dev file takes the test rows as they are (test v1 is newer: `lines` units, procedure for
   radiation, ...). Then dev, test and every handoff bundle have the same ①-b for each criterion_id.
The originals are kept as concepts.orig.json / criteria.orig.jsonl next to the files (written once).

Usage (stage2 folder): python3 fix_ctgov_units.py
Then: python3 check_concepts.py --concepts ../ctgov_v2/test/concepts.json --criteria ../ctgov_v2/test/criteria.jsonl \
          --ref-criteria ../ctgov_v1/criteria.jsonl
"""
import json, os, shutil

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ctgov_v2")

ALT_UNITS = {
    "cd4_count": {"cells/mm3": 1, "cells/mm^3": 1, "/mm3": 1, "/uL": 1},
    "life_expectancy": {"year": 12, "month": 1},
    "platelet_count": {"E9/L": 1, "G/L": 1},
    "eosinophil_count": {"G/L": 1, "E9/L": 1, "x10^9/L": 1},
    "body_weight": {"pounds": 0.453592, "lbs": 0.453592},
    "hiv_viral_load": {"cps/mL": 1},
    "creatinine_clearance": {"cc/min": 1, "mL/min/1.73m2": 1, "mL/min/1.73m^2": 1},   # body-surface normalised clearance
    "creatinine": {"uM": 0.0113, "µM": 0.0113, "µmol/L": 0.0113},
    "c_peptide": {"pmol/mL": 3.02},                                                    # pmol/mL = nmol/L
    "urine_protein_24h": {"mg": 0.001, "g": 1},                                        # 24 h collection implied
    "hbv_dna": {"copies/mL": 0.172},                                                   # approx. 5.82 copies = 1 IU
}

# 4th meeting (2026-10-25), item 3 (proposed by the Agent 3 owner; not yet in the Agent 1 / CT.gov original): record-answerable tissue / contraception items are not administrative
DEV_ADMIN_FALSE = {
    "NCT07720284-I08": "SYN-0019 gold PASS from TURBT pathology (archival tumour on record) -> not administrative (안건 3)",
    "NCT07566156-I02": "SYN-0019 gold PASS from TURBT pathology (tissue on record) -> not administrative (4차 회의 안건 3, 2026-10-25)",
    "NCT06692738-I04": "SYN-0011 gold PASS from PD-L1 TPS 70% (tumor sample result on record) -> not administrative (안건 3)",
    "NCT03424005-I09": "SYN-0017 gold PASS from iliac biopsy (ER+, HER2 0) -> not administrative (안건 3)",
    "NCT02714634-I09": "SYN-0010 gold PASS from progestin implant (birth-control method on record) -> not administrative (안건 3)",
}

ROW_FIXES = {
    "NCT04005690-I19": ({"unit": "cells/mm3"}, "단위 'mm^3'을 'cells/mm3'로 (같은 단위, 표기만 정리)"),
    "NCT07815704-I07": ({"unit": "/uL"}, "원문 'Platelet count > 100,000 mL'은 /µL의 오타로 판단 (100 x10^9/L). 값은 그대로"),
    "NCT07156227-I13": ({"unit": "g/dL"}, "원문 'Albumin > 2.5 mg/dL'은 g/dL의 오타로 판단 (2.5 g/dL가 표준 역치). 값은 그대로"),
    "NCT07412210-E12": ({"unit": "mL/min/1.73m2"}, "원문 'ml/min/m^2'는 eGFR 표준 단위 mL/min/1.73m2로 판단"),
    "NCT03643549-I18": ({"parse_status": "free_text", "concept": None, "operator": None, "value": None, "unit": None},
                        "'within normal limit'은 수치 역치가 없어 기록의 참고 범위로 판정 (free_text, 다른 free_text 행과 같은 형식). 수치 코드 판정 대상 아님"),
}

# Same rule on test (agreed 2026-10-25): of the 71 test rows Agent 3 v3 listed (admin_review_candidates_test.csv),
# 14 can be settled from the record -> administrative false. The other 57 (consent, willingness, agreement to
# future contraception or sample donation, procedural notes) stay administrative.
R = " (합성 담당, 2026-10-25, 4차 회의 안건 3 기준)"
TEST_ADMIN_FALSE = {
    "NCT06172478-I28": "tissue sample from a biopsy since progression: biopsy history is on record" + R,
    "NCT06630130-I12": "current contraceptive method, breastfeeding, pregnancy test, menopause: on record" + R,
    "NCT06695845-I04": "adequate tumor sample: tissue availability is on record" + R,
    "NCT06731478-I06": "tumor sample (FFPE or new biopsy): tissue availability is on record" + R,
    "NCT06023862-I08": "FFPE block or slides available: on record" + R,
    "NCT06840002-I02": "fresh or archived tissue available: on record" + R,
    "NCT07287150-I04": "suitable tumor tissue available: on record" + R,
    "NCT07181161-I06": "archival or new FFPE sample: tissue availability is on record" + R,
    "NCT03643549-I03": "paraffin block / tumour tissue from surgery: on record" + R,
    "NCT03643549-I21": "must use adequate contraception (no time limit): current method is on record" + R,
    "NCT07472517-I03": "archival FFPE tissue available: on record" + R,
    "NCT07063212-I09": "not pregnant, not breastfeeding, childbearing potential: on record (agreement part remains)" + R,
    "NCT07213609-I03": "archival or fresh FFPE sample: tissue availability is on record" + R,
    "NCT07222956-I07": "sterilisation, menopause, negative hCG at screening: on record (agreement part remains)" + R,
}


def backup(path, orig):
    if not os.path.exists(orig):
        shutil.copyfile(path, orig)


def main():
    for split in ("dev", "test"):
        p = os.path.join(ROOT, split, "concepts.json")
        backup(p, os.path.join(ROOT, split, "concepts.orig.json"))
        concepts = json.load(open(os.path.join(ROOT, split, "concepts.orig.json"), encoding="utf-8"))
        n = 0
        for c in concepts:
            for u, f in ALT_UNITS.get(c["key"], {}).items():
                alt = c.setdefault("alt_units", None) or {}
                if u not in alt:
                    alt[u] = f
                    n += 1
                c["alt_units"] = alt
        json.dump(concepts, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{split}: concepts.json +{n} alt_units")

    p = os.path.join(ROOT, "test", "criteria.jsonl")
    orig = os.path.join(ROOT, "test", "criteria.orig.jsonl")
    backup(p, orig)
    rows, done = [], set()
    for line in open(orig, encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        if c["criterion_id"] in ROW_FIXES:
            change, note = ROW_FIXES[c["criterion_id"]]
            c.update(change)
            c["fix_note"] = note + " (합성 담당, 2026-10-22)"
            done.add(c["criterion_id"])
        if c["criterion_id"] in TEST_ADMIN_FALSE:
            c["administrative"] = False
            c["fix_note"] = ((c.get("fix_note") or "") + " / " if c.get("fix_note") else "") + "not administrative: " + TEST_ADMIN_FALSE[c["criterion_id"]]
            done.add(c["criterion_id"])
        rows.append(c)
    with open(p, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in rows)
    print(f"test: criteria.jsonl {len(done)}/{len(ROW_FIXES) + len(TEST_ADMIN_FALSE)} rows fixed; missing {sorted((set(ROW_FIXES) | set(TEST_ADMIN_FALSE)) - done)}")

    test_rows = {c["criterion_id"]: c for c in rows}
    p = os.path.join(ROOT, "dev", "criteria.jsonl")
    orig = os.path.join(ROOT, "dev", "criteria.orig.jsonl")
    backup(p, orig)
    out, n, trials = [], 0, set()
    for line in open(orig, encoding="utf-8"):
        if not line.strip():
            continue
        c = json.loads(line)
        t = test_rows.get(c["criterion_id"])
        if t is not None:
            trials.add(c["trial_id"])
            if t != c:
                c, n = t, n + 1
        if c["criterion_id"] in DEV_ADMIN_FALSE:
            c = dict(c, administrative=False, fix_note=DEV_ADMIN_FALSE[c["criterion_id"]])
        out.append(c)
    with open(p, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in out)
    print(f"dev: criteria.jsonl {n} rows taken from test for {len(trials)} shared trials {sorted(trials)}")


if __name__ == "__main__":
    main()
