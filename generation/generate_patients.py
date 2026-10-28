#!/usr/bin/env python3
"""Stage 1 synthetic patient generator (LLM API) -> shared ② Patient Record format.

Reads patient specs (same shape as specs.json), asks an LLM to write a fictional
multi-document record per spec, validates it, retries on errors, and appends to
an output JSONL with new opaque patient IDs.

Examples:
  # see the prompt without calling any API
  python3 generate_patients.py --specs specs_new_example.json --dry-run

  # Anthropic (pip install anthropic; export ANTHROPIC_API_KEY=...)
  python3 generate_patients.py --specs specs_new_example.json --provider anthropic --model <model-id>

  # OpenAI (pip install openai; export OPENAI_API_KEY=...)
  python3 generate_patients.py --specs specs_new_example.json --provider openai --model <model-id>

Outputs (default, next to this script):
  patients_generated.jsonl   new ② records (appended)
  id_map_generated.json      patient_id -> base_id (keep away from agents)
  generation_log.jsonl       provider, model, attempts, warnings per patient
"""
import argparse, json, os, random, re, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate import check  # noqa: E402

PROMPT = open(os.path.join(HERE, "prompt_generate_patient.md")).read()


def spec_text(s):
    lines = [f"- base_id: {s['base_id']}", f"- sex: {s['sex']}"]
    lines.append(f"- age: {s['age_months']} months" if "age_months" in s else f"- age: {s['age']} years")
    lines.append(f"- main condition: {s['condition']}")
    if s.get("history"):
        lines.append(f"- relevant history: {', '.join(s['history'])}")
    if s.get("meds"):
        lines.append(f"- medications (current or past): {', '.join(s['meds'])}")
    if s.get("seed_summary"):
        lines.append(f"- use exactly this summary sentence: {s['seed_summary']}")
    if s.get("notes"):
        lines.append(f"- extra notes: {s['notes']}")
    return "\n".join(lines)


def example_text(path):
    """One existing record (without IDs) as a style example."""
    if not os.path.exists(path):
        return "(no example available)"
    p = json.loads(open(path).readline())
    ex = {"summary": p["summary"],
          "documents": [{k: d[k] for k in ("type", "date", "author_role", "text")} for d in p["documents"]]}
    return json.dumps(ex, ensure_ascii=False, indent=1)


def call_llm(provider, model, prompt, temperature):
    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic()
        kw = dict(model=model, max_tokens=4000, messages=[{"role": "user", "content": prompt}])
        try:
            r = client.messages.create(temperature=temperature, **kw)
        except (TypeError, anthropic.BadRequestError) as e:
            # some SDK versions / models do not accept temperature: retry once without it
            if "temperature" not in str(e).lower():
                raise
            r = client.messages.create(**kw)
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI()
        kw = dict(model=model, messages=[{"role": "user", "content": prompt}],
                  response_format={"type": "json_object"})
        try:
            r = client.chat.completions.create(temperature=temperature, **kw)
        except Exception as e:
            if "temperature" not in str(e).lower():
                raise
            r = client.chat.completions.create(**kw)
        return r.choices[0].message.content
    raise ValueError(f"unknown provider {provider}")


FATAL_ERRORS = {"AuthenticationError", "PermissionDeniedError", "NotFoundError"}
PACKAGES = {"anthropic": ("anthropic", "ANTHROPIC_API_KEY"), "openai": ("openai", "OPENAI_API_KEY")}


def preflight(provider):
    """Stop before any patient is processed if the SDK or API key is missing."""
    module, key = PACKAGES[provider]
    try:
        __import__(module)
    except ImportError:
        sys.exit(f"STOP: the '{module}' package is not installed for this Python ({sys.executable}).\n"
                 f"Install it with:  {sys.executable} -m pip install {module}")
    if not os.environ.get(key):
        sys.exit(f"STOP: environment variable {key} is not set.  export {key}=...")


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def to_record(raw, pid, as_of):
    docs = sorted(raw["documents"], key=lambda d: d["date"])
    return {"patient_id": pid, "as_of": as_of, "summary": raw["summary"].strip(),
            "documents": [{"doc_id": f"{pid}-D{i:02d}", "type": d["type"], "date": d["date"],
                           "author_role": d["author_role"], "text": d["text"].strip()}
                          for i, d in enumerate(docs, 1)]}


def existing_ids(paths):
    ids = set()
    for p in paths:
        if os.path.exists(p):
            for line in open(p):
                if line.strip():
                    ids.add(json.loads(line)["patient_id"])
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--provider", choices=["anthropic", "openai"])
    ap.add_argument("--model", help="model id for the provider")
    ap.add_argument("--out", default=os.path.join(HERE, "patients_generated.jsonl"))
    ap.add_argument("--id-map", default=os.path.join(HERE, "id_map_generated.json"))
    ap.add_argument("--example", default=os.path.join(HERE, "patients.jsonl"))
    ap.add_argument("--reserved", nargs="*", default=[os.path.join(HERE, "patients.jsonl")],
                    help="JSONL files whose patient_ids must not be reused")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="print the first prompt and exit")
    a = ap.parse_args()

    specs = json.load(open(a.specs))
    as_of = specs["as_of"]
    example = example_text(a.example)

    if a.dry_run:
        print(PROMPT.format(spec=spec_text(specs["patients"][0]), as_of=as_of, example=example,
                            age=specs["patients"][0].get("age", "N")))
        return
    if not (a.provider and a.model):
        ap.error("--provider and --model are required unless --dry-run")
    preflight(a.provider)

    used = existing_ids(a.reserved + [a.out])
    pool = [n for n in range(1, 10000) if f"SYN-{n:04d}" not in used]
    random.Random(a.seed).shuffle(pool)
    id_map = json.load(open(a.id_map)) if os.path.exists(a.id_map) else {}

    for spec in specs["patients"]:
        pid = f"SYN-{pool.pop():04d}"
        prompt = PROMPT.format(spec=spec_text(spec), as_of=as_of, example=example, age=spec.get("age", "N"))
        record, errs, warns = None, [], []
        for attempt in range(1, a.retries + 1):
            try:
                text = call_llm(a.provider, a.model, prompt, a.temperature)
            except Exception as e:
                if type(e).__name__ in FATAL_ERRORS:  # retrying will not help: stop the whole run
                    sys.exit(f"STOP: {type(e).__name__}: {e}\n(check API key and --model; nothing more was sent)")
                errs = [f"api: {type(e).__name__}: {e}"]
                continue
            try:
                rec = to_record(parse_json(text), pid, as_of)
            except Exception as e:  # bad JSON or missing keys
                errs = [f"parse: {e}"]
                continue
            errs, warns = [], []
            check(rec, errs, warns)
            if not errs:
                record = rec
                break
            prompt += "\n\nYour previous answer had these problems, fix them:\n" + "\n".join(errs)
        log = {"base_id": spec["base_id"], "patient_id": pid, "provider": a.provider, "model": a.model,
               "attempts": attempt, "ok": record is not None, "errors": errs, "warnings": warns,
               "created": date.today().isoformat()}
        with open(os.path.join(os.path.dirname(a.out), "generation_log.jsonl"), "a") as f:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")
        if record is None:
            print(f"FAIL {spec['base_id']}: {errs}")
            continue
        with open(a.out, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        id_map[pid] = spec["base_id"]
        json.dump(id_map, open(a.id_map, "w"), indent=2)
        print(f"OK   {spec['base_id']} -> {pid} ({len(record['documents'])} docs, {len(warns)} warnings)")


if __name__ == "__main__":
    main()
