You are labeling a synthetic clinical-trial matching dataset. Decide, criterion by criterion, whether the patient below can be enrolled in the trial below, using ONLY what is written in the patient's documents.

## Judgment date (as_of)
{as_of}. All time windows ("within 28 days", "in the last 6 months") are counted back from this date, using each document's date. Treat as_of as "today": the record is frozen at that date. If you were given any other current date (for example in a system message), ignore it. Each document header shows how many days before as_of it was written; use that number instead of computing dates yourself.

## Patient
{patient}

## Trial
{trial}

## Criteria to judge
Each line: criterion_id | type | cohort | text
{criteria}

## How to judge each criterion

Status means "does this criterion allow enrollment?" (for exclusion criteria too):
- PASS: the record shows the requirement is met (inclusion) or the excluding condition is absent (exclusion). Absence counts only when the record says so explicitly (e.g. "no history of ILD", "HBsAg negative", "never smoker"). A criterion that cannot apply to this patient (e.g. pregnancy test rules for a male patient, a dose-modification rule for a drug the patient never received) is PASS.
- FAIL: the record shows the requirement is not met, or the excluding condition is present.
- UNKNOWN: the record does not settle it.
- CONFLICT: two documents give contradicting information that decides this criterion, and neither clearly supersedes the other (a newer lab result simply replaces an older one; that is not a conflict). A record from another source (outside records, another hospital, pharmacy, referral letter) that states a diagnosis, treatment, allergy or result contradicting what another document states or denies (e.g. "No prior malignancy" vs an outside note of a resected cancer) is CONFLICT with action clinician_confirmation, even when one side is more detailed: do not decide which source is right. Only a newer measurement of a value that can change (lab, vital sign, imaging) replaces an older one.

Reason (must match the status):
- PASS -> VALID
- FAIL -> VIOLATED
- CONFLICT -> CONFLICT
- UNKNOWN -> MISSING (nothing in the record), EXPIRED (the information exists but is older than the criterion's time window), or UNSUPPORTED (something related is written, but it does not prove the criterion, e.g. "HER2 status pending", "chest feels fine" for an LVEF threshold).

Do not assume normal values or absent diseases. If an exclusion condition is never mentioned, it is UNKNOWN / MISSING, not PASS.
Recency: a test or scan shows the patient's state only around its date. When a criterion is about the patient's current state (e.g. "no active brain metastases", "measurable disease", "adequate organ function") and gives no time window, an imaging result older than 90 days before as_of, or a lab result older than 30 days, does not prove it: use UNKNOWN / EXPIRED with action new_test (imaging) or lab_check (labs), quoting the old result. The same applies, regardless of age, when a later document says the test has not been repeated or the situation has changed. Fixed facts (histology, mutation results, past treatments, diagnoses) do not expire.

Judgment words: when a criterion depends on a judgment word without a threshold ("clinically significant", "uncontrolled", "severe", "in the investigator's opinion"), do not decide it as FAIL yourself. If the record describes a related finding (e.g. grade 2 neuropathy for "clinically significant toxicity"), use UNKNOWN / UNSUPPORTED with action clinician_confirmation and quote the finding. Use FAIL only when the record itself states the condition in the criterion's own terms.

Suspected is not diagnosed: a diagnosis that the record calls suspected, possible, probable, "features of", "concerning for", "rule out", or still under work-up is not a confirmed diagnosis. For a criterion that requires the diagnosis, use UNKNOWN / UNSUPPORTED (quote the finding, action new_test or clinician_confirmation), not PASS and not FAIL.

Do not infer what the record does not state: do not decide a criterion from events, needs or states that are not written down, such as a future ICU need, a planned treatment's outcome, or a severity grade nobody assigned. If the criterion depends on such a thing, use UNKNOWN (MISSING if nothing related is written, UNSUPPORTED if something related is).

Option-list fragments: some criterion lines are one option out of a list of alternatives that the parser split apart (e.g. a line that only says "Hormone receptor status not specified" or "ECOG 2" with no requirement verb). Do not FAIL a patient only because they match a different option. Read the neighbouring criteria: if they show the patient matches one of the allowed options, use PASS for this line and quote the fact that matches the allowed option; otherwise use UNKNOWN / UNSUPPORTED with action clinician_confirmation.

Unspecified lab thresholds: for "adequate hematologic / renal / hepatic / organ function" without numbers, use PASS if the most recent relevant labs (within the recency rule above) are all within normal or near-normal ranges, quoting them; if any value is clearly abnormal, use UNKNOWN / UNSUPPORTED with action clinician_confirmation; if labs are missing or too old, follow the rules for MISSING / EXPIRED.

Purely administrative or investigator-judgment criteria (informed consent, willingness to comply, "any condition that in the investigator's opinion...") are UNKNOWN / MISSING with action clinician_confirmation, unless the record explicitly addresses them.

Cohorts: if the trial has several cohorts/parts, pick the one this patient would most plausibly enter and report it in "cohort_assignment". A criterion whose cohort label (or wording) restricts it to a different cohort gets "applies": false. Cohort labels come from a rule-based parser and can be wrong: decide applicability from the criterion text itself when the label looks inconsistent. All other criteria get "applies": true.

expected_action (what the system should do next for this criterion):
- PASS or FAIL -> none
- otherwise one of: patient_question (the patient can answer, e.g. symptoms, pregnancy plans, willingness), med_record_check (likely in records not shown, e.g. past diagnoses), lab_check (a recent lab result is needed), med_history_check (prior treatments and their dates), clinician_confirmation (needs a clinician's judgment), new_test (needs a test that was never done, e.g. a biomarker).

Evidence: for every criterion with status PASS, FAIL or CONFLICT, and for UNKNOWN with reason EXPIRED or UNSUPPORTED, quote the supporting text. Each quote must be copied character for character from one document's text (a short span, ideally under 120 characters) together with its doc_id. Never shorten a quote with "..." and use ordinary spaces; if two separate phrases are needed, give two quotes. For CONFLICT give the quotes from both sides. For UNKNOWN / MISSING give no evidence.

## Output
Return only a JSON object, no markdown fences:
{{
  "cohort_assignment": "<cohort name or null>",
  "criteria": [
    {{"criterion_id": "...", "applies": true, "expected_status": "PASS|FAIL|UNKNOWN|CONFLICT",
      "reason": "VALID|VIOLATED|MISSING|EXPIRED|UNSUPPORTED|CONFLICT",
      "evidence": [{{"doc_id": "...", "quote": "..."}}],
      "expected_action": "none|patient_question|med_record_check|lab_check|med_history_check|clinician_confirmation|new_test",
      "rationale": "<one short sentence>"}}
  ]
}}
Include every criterion_id listed above exactly once, in the same order.
