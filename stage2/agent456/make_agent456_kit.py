#!/usr/bin/env python3
"""Build handoff/for_agent456_v1.zip: everything Agents 4 (verifier), 5 (information acquisition) and 6 (ranking)
need to develop and self-score on dev. Test answers and the test variant map are never included.
Sources: handoff/for_agent3_v10.zip (dev data), agent2_workspace/_archive/agent3_kit_v14_9.zip (evidence),
agent3_workspace/received/agent3_a3-0.3.0.zip (Agent 3 final dev base + variant output on kit v14.9 = Agent 4/5 input), stage2/variants/final_dev.
Usage (repo root): python3 stage2/agent456/make_agent456_kit.py
"""
import csv, io, json, os, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(HERE, ".."))
import gold_lib as G  # noqa: E402

NAME = "for_agent456_v5"
A3 = os.path.join(ROOT, "handoff/for_agent3_v10.zip")
KIT = os.path.join(ROOT, "agent2_workspace/_archive/agent3_kit_v14_9.zip")   # for_agent456_v4 was built on v14.9 (Agent 3 v3 baseline); moved 2026-10-27 when v14.12 arrived
A3OUT = os.path.join(ROOT, "agent3_workspace/received/agent3_a3-0.3.0.zip")   # final a3-0.3.0 package (2026-10-27)
VAR = os.path.join(ROOT, "stage2/variants/final_dev")


def main():
    files = {}
    za = zipfile.ZipFile(A3)
    for n in za.namelist():
        if n.startswith("for_agent3_v10/dev/") and not n.endswith("/"):
            files["dev/" + n[len("for_agent3_v10/dev/"):]] = za.read(n)
    files["common_format_v0.5.md"] = za.read("for_agent3_v10/common_format_v0.5.md")
    files["AGENT3_NOTES_trialgpt.md"] = za.read("for_agent3_v10/AGENT3_NOTES_trialgpt.md")
    zk = zipfile.ZipFile(KIT)
    for n in zk.namelist():
        b = os.path.basename(n)
        if b.startswith(("evidence_dev_haiku_v14_9", "evidence_dev_rules_v14_9", "evidence_dev_variants_")) and b.endswith(".jsonl") and "changes" not in b:
            files["dev/evidence/" + b] = zk.read(n)
        if b in ("AGENT2_OUTPUT_FOR_AGENT3.md", "evidence_index.py"):
            files[("dev/evidence/" if b.endswith(".py") else "") + b] = zk.read(n)
    z3 = zipfile.ZipFile(A3OUT)
    root3 = "agent3_a3-0.3.0/"
    pre = root3 + "handoff_agent4/"
    runs = {root3 + "runs/dev_v10_kit149_p07/": "dev/agent3_out_v3_p07/",                 # base 54 pairs, evidence v14.9
            root3 + "runs/dev_variants_v10_kit149_p07/": "dev/agent3_out_v3_p07_variants/"}  # variants 100 pairs
    for n in z3.namelist():
        if n.endswith("/"):
            continue
        if n.startswith(pre) and "/dev_agent3_out_v3_p07/" not in n:      # the older v14.7 run is replaced by the runs below
            files["dev/agent3_handoff/" + n[len(pre):]] = z3.read(n)
        for src, dst in runs.items():
            if n.startswith(src):
                files[dst + n[len(src):]] = z3.read(n)
    files["dev/agent3_handoff/FREEZE_a3-0.3.0.json"] = z3.read(root3 + "FREEZE_a3-0.3.0.json")

    # variant ranking gold (common format 6.4, same function as the base ranking gold)
    T = {t["trial_id"]: t for t in (json.loads(l) for l in files["dev/reference/trials.jsonl"].decode().splitlines() if l.strip())}
    GV = [json.loads(l) for l in files["dev/gold/gold_variants.jsonl"].decode().splitlines() if l.strip()]
    files["dev/gold/ranking_gold_variants.jsonl"] = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in G.ranking_rows(GV, T)).encode()

    # eval tables
    M = json.load(open(os.path.join(VAR, "id_map_variants_private.json")))
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["variant_patient_id", "base_patient_id", "variant", "trial_id", "target_criterion", "changed_doc_id", "expected_status",
                "expected_reason", "expected_action", "trial_label", "note"])
    for g in GV:
        inj = g.get("injection") or {}
        if not inj.get("doc_id"):
            continue
        c = next(x for x in g["criteria"] if x["criterion_id"] == inj["target_criterion"])
        w.writerow([g["patient_id"], M[g["patient_id"]]["base_patient_id"], inj["variant"], g["trial_id"], c["criterion_id"], inj["doc_id"],
                    c["expected_status"], c["reason"], c["expected_action"], g["trial_label"], inj["note"]])
    files["dev/eval/variant_targets.csv"] = ("﻿" + buf.getvalue()).encode()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["variant_patient_id", "base_patient_id", "changed_doc_id", "base_doc_id"])
    base_docs = {d["doc_id"] for l in files["dev/input/patients.jsonl"].decode().splitlines() if l.strip()
                 for d in json.loads(l)["documents"]}
    for g in GV:
        inj = g.get("injection") or {}
        if inj.get("doc_id"):
            b = M[g["patient_id"]]["base_patient_id"]
            bd = inj["doc_id"].replace(g["patient_id"] + "-", b + "-", 1)
            w.writerow([g["patient_id"], b, inj["doc_id"], bd if bd in base_docs else "(new document)"])
    files["dev/eval/update_pairs.csv"] = ("﻿" + buf.getvalue()).encode()
    files["dev/eval/eval_variants.py"] = open(os.path.join(HERE, "eval_variants.py"), "rb").read()
    files["README.md"] = open(os.path.join(HERE, "README_for_agent456.md"), "rb").read()

    out = os.path.join(ROOT, f"handoff/{NAME}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, b in sorted(files.items()):
            z.writestr(f"{NAME}/{p}", b)
    print(f"{len(files)} files -> {out}")


if __name__ == "__main__":
    main()
