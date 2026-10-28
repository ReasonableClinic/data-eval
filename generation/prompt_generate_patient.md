You are writing a FICTIONAL electronic health record for a synthetic patient. The record will be used to test a clinical-trial matching system, so it must read like real clinical documentation, not like a trial eligibility checklist.

## Patient specification
{spec}

## Reference date
as_of = {as_of}. Every document date must be on or before this date. Ages must be computed at as_of.

## Rules
1. Write 5 to 8 documents. The first is a `registration` document whose text starts exactly with "Male. DOB YYYY-MM-DD." or "Female. DOB YYYY-MM-DD." followed by an occupation. Choose a DOB that gives the specified age at as_of.
2. Allowed document types: registration, clinic_note, lab_result, medication_record, imaging_report, pathology_report, patient_interview, discharge_summary.
   Allowed author_role values: physician, nurse, lab, pharmacy, patient, clerk. Use `patient` only for patient_interview.
3. Write like real notes: abbreviations (e.g. "c/o", "PMH", "Imp:"), units with reference ranges where natural, dates of procedures and drug starts/stops, doses.
4. Do NOT write in trial language. Never use words such as "eligible", "inclusion", "exclusion", "criteria", "prior to enrollment", "at screening". Do not list negatives that a clinician would not normally document.
5. Leave natural gaps: not every lab is checked at every visit, some facts appear in only one document, some results are a few months old. Do not invent a clean summary of everything.
6. Keep numbers and dates internally consistent across documents (diagnosis before treatment, treatment start before stop, age matches DOB).
7. No personal identifiers: no names, addresses, phone numbers, hospital names, or record numbers.
8. `summary` is 1-2 sentences in the style of a medical-exam vignette, starting with "A {age}-year-old ..." (or "A N-month-old ..." for infants).

## Example of the expected style (another patient)
{example}

## Output
Return ONLY a JSON object, no markdown fences:
{{"summary": "...", "documents": [{{"type": "...", "date": "YYYY-MM-DD", "author_role": "...", "text": "..."}}]}}
