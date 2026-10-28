You are extending a FICTIONAL electronic health record of a synthetic patient. The record is used to test a clinical-trial matching system. Real records contain a comprehensive history and a recent laboratory panel; this record does not yet. Add them.

## Patient specification
{spec}

## Existing record (do not change it; your documents must agree with it)
{record}

## Reference date
as_of = {as_of}. Both new documents must be dated between {first_date} and {as_of} (inclusive).

## Write exactly two new documents

1. A `clinic_note` by a `physician`: a comprehensive history and physical (H&P) done at the most recent encounter, written like a real note with headings. Include, as a clinician would normally document them:
   - Vitals: height, weight, BMI, BP, HR, temperature, SpO2 (pediatric: weight and height with percentiles; infant: weight, length, head circumference).
   - Past medical history as a list, each with year of diagnosis, then a line that the rest of the history is negative for the major organ systems (e.g. "No other cardiac, pulmonary, hepatic, renal, autoimmune or neurologic history. No prior malignancy." — adapted to what is true for this patient).
   - Past surgical history; allergies (with reaction, or "NKDA").
   - Medication reconciliation: every current medication with dose and start year; recently stopped ones with stop date and reason. Must match the existing record.
   - Social history: smoking (pack-years), alcohol, substances, occupation; family history in one line.
   - For female patients aged 12-55: menstrual / menopausal status and contraception or pregnancy status as normally recorded. For others: omit.
   - Review of systems with pertinent negatives, and a focused physical exam.
   - The standard objective assessment for the main condition that a specialist would have in the chart, with values: e.g. ECOG and current staging for cancer; spirometry (FEV1, FEV1/FVC, % predicted) and exacerbation count for COPD/asthma; echocardiogram (LVEF, LV dimensions) and NYHA class for heart failure; HbA1c trend for diabetes; disease activity score for rheumatologic disease; cognitive scores for dementia; visual acuity / exam for eye disease; age-appropriate developmental and feeding notes for an infant. Use values consistent with the existing record and the severity described.
   - Assessment and plan in 2-4 lines.
2. A `lab_result` by `lab`: a recent routine panel with units and reference ranges: CBC with differential, comprehensive metabolic panel (creatinine, eGFR, electrolytes, ALT, AST, bilirubin, albumin), and what is routine for this patient's age and conditions (e.g. HbA1c, lipids, TSH, INR, urinalysis, hepatitis B/C and HIV serology when a clinician would check them). Values must fit the existing record (same direction and size as earlier results, plausible change over time).

## Rules
- Do not contradict anything in the existing record (diagnoses, dates, doses, test results, sex, age). If something is unknown in the record, choose something clinically plausible and keep it consistent.
- When you restate earlier results, keep their values and their interpretation exactly. Do not add new findings to an earlier test report and do not upgrade an interpretation (e.g. do not call a partial response a remission, or a borderline value normal). New measurements belong to the new documents with their own date.
- Do not add a new major diagnosis that is not in the specification or the record. Minor common findings are allowed when plausible.
- Do not write in trial language. Never use words such as "eligible", "inclusion", "exclusion", "criteria", "trial", "prior to enrollment", "at screening".
- No personal identifiers (no names, addresses, hospital names, record numbers).
- Write in English, in the same style and abbreviations as the existing record.

## Output
Return ONLY a JSON object, no markdown fences:
{{"documents": [{{"type": "clinic_note", "date": "YYYY-MM-DD", "author_role": "physician", "text": "..."}}, {{"type": "lab_result", "date": "YYYY-MM-DD", "author_role": "lab", "text": "..."}}]}}
