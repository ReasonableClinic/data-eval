# Hand-written record edits for the dev variant set (2026-10-23). One document changes per variant.
import json
E = []
def add(**k): E.append(k)

# ---------------- SYN-0001 (7-year-old, nephrotic syndrome)
add(base="SYN-0001", variant="violation", criterion_id="NCT05003986-E14", doc_id="SYN-0001-D08",
    replace=[["Potassium 4.0 mmol/L (ref 3.5-5.0)", "Potassium 5.9 mmol/L (ref 3.5-5.0) H"]],
    evidence=[{"quote": "Potassium 5.9 mmol/L (ref 3.5-5.0) H", "concept": "potassium", "value": 5.9, "unit": "mmol/L"}],
    action="none", note="screening potassium 5.9 > 5.5 mmol/L", check_terms=["potassium", "K+", "hyperkal"])
add(base="SYN-0001", variant="missing", criterion_id="NCT05003986-E14", doc_id="SYN-0001-D08",
    replace=[["Potassium 4.0 mmol/L (ref 3.5-5.0)\n", ""]],
    action="lab_check", note="potassium line removed from the screening panel; no other potassium value",
    check_terms=["potassium", "K+", "electrolytes"])
add(base="SYN-0001", variant="unsupported", criterion_id="NCT07674147-E21", doc_id="SYN-0001-D07",
    replace=[["No NSAIDs, no antibiotics, no supplements.", "Mother is unsure which over-the-counter pain medicines were given at home before the visit."]],
    evidence=[{"quote": "Mother is unsure which over-the-counter pain medicines were given at home before the visit.", "concept": "medication", "term": "over-the-counter pain medicines", "value": None, "unit": None}],
    action="patient_question", note="NSAID denial replaced by an unclear OTC analgesic history: NSAID use in the last 14 days cannot be ruled out or shown",
    check_terms=["NSAID", "ibuprofen", "naproxen"])

# ---------------- SYN-0002 (HBV cirrhosis, HCC)
add(base="SYN-0002", variant="missing", criterion_id="NCT07774247-E23", doc_id="SYN-0002-D08",
    replace=[["HIV-1/2 Ag/Ab non-reactive\n", ""]],
    action="lab_check", note="HIV test removed from the viral studies; no other HIV result", check_terms=["HIV"])
add(base="SYN-0002", variant="unsupported", criterion_id="NCT06582017-E04", doc_id="SYN-0002-D09",
    replace=[["ALLERGIES: NKDA.", "ALLERGIES: patient recalls a reaction to an injection years ago; drug and details not available."]],
    evidence=[{"quote": "ALLERGIES: patient recalls a reaction to an injection years ago; drug and details not available.", "concept": "allergy", "term": "reaction to an injection", "value": None, "unit": None}],
    action="patient_question", note="NKDA replaced by an unidentified past injection reaction: hypersensitivity to the study product components cannot be ruled out or shown",
    check_terms=["NKDA", "allerg"])

# ---------------- SYN-0004 (diabetic kidney disease)
add(base="SYN-0004", variant="violation", criterion_id="NCT07849348-E16", doc_id="SYN-0004-D08",
    replace=[["TSH 2.4 mIU/L (0.4-4.0)", "TSH 8.7 mIU/L (0.4-4.0) H"]],
    evidence=[{"quote": "TSH 8.7 mIU/L (0.4-4.0) H", "concept": "tsh", "value": 8.7, "unit": "mIU/L"}],
    action="none", note="TSH 8.7 > 6.0 mIU/L", check_terms=["TSH", "thyroid"])
add(base="SYN-0004", variant="conflict", criterion_id="NCT06110130-E04", doc_id="NEW",
    new_doc={"type": "clinic_note", "date": "2026-09-10", "author_role": "physician",
             "text": "Outside nephrology letter (received by fax). Known to our clinic since 2019. Kidney biopsy 2019: IgA nephropathy with mesangial proliferation. Proteinuria followed since. Copy sent to primary nephrologist."},
    evidence=[{"quote": "Kidney biopsy 2019: IgA nephropathy with mesangial proliferation.", "concept": "diagnosis", "term": "IgA nephropathy", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="outside letter reports a 2019 biopsy showing IgA nephropathy; the clinic note says no renal biopsy",
    check_terms=["biopsy", "IgA", "glomerulonephritis"])
add(base="SYN-0004", variant="unsupported", criterion_id="NCT06600412-E02", doc_id="SYN-0004-D07",
    replace=[["No prior malignancy.", "Seen by oncology in 2024 for an abnormal finding; follow-up details not in our records."]],
    evidence=[{"quote": "Seen by oncology in 2024 for an abnormal finding; follow-up details not in our records.", "concept": "diagnosis", "term": "abnormal finding seen by oncology", "value": None, "unit": None}],
    action="med_record_check", note="malignancy denial replaced by an oncology visit with unknown outcome: ongoing cancer treatment cannot be ruled out or shown",
    check_terms=["malignan", "cancer", "oncolog", "chemo"])

# ---------------- SYN-0005 (mucormycosis, on amphotericin B)
add(base="SYN-0005", variant="violation", criterion_id="NCT06756191-E03", doc_id="SYN-0005-D09",
    replace=[["ALT 38 U/L (7-56)", "ALT 412 U/L (7-56) H"]],
    evidence=[{"quote": "ALT 412 U/L (7-56) H", "concept": "alt", "value": 412, "unit": "U/L"}],
    action="none", note="ALT 412 U/L > 5 x ULN (280)", check_terms=["ALT", "LFT", "transaminase", "liver function"])
add(base="SYN-0005", variant="conflict", criterion_id="NCT06756191-E02", doc_id="NEW",
    new_doc={"type": "medication_record", "date": "2026-09-20", "author_role": "pharmacy",
             "text": "Pharmacy allergy record (community pharmacy profile): Fluconazole - hives (2019). No other recorded drug allergies."},
    evidence=[{"quote": "Fluconazole - hives (2019).", "concept": "allergy", "term": "fluconazole", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="pharmacy profile lists a fluconazole (azole) allergy; the physician note says NKDA",
    check_terms=["NKDA", "allerg", "azole"])

# ---------------- SYN-0006 (MCI due to AD)
add(base="SYN-0006", variant="violation", criterion_id="NCT06786676-I04", doc_id="SYN-0006-D08",
    replace=[["Wt 66 kg, BMI 24.8", "Wt 94 kg, BMI 35.4"]],
    evidence=[{"quote": "Wt 94 kg, BMI 35.4", "concept": "body_weight", "value": 94, "unit": "kg"}],
    action="none", note="weight 94 kg > 90 kg and BMI 35.4 > 29.9", check_terms=["Wt ", "weight", "BMI", " kg"])
add(base="SYN-0006", variant="unsupported", criterion_id="NCT07589595-E03", doc_id="SYN-0006-D08",
    replace=[["No prior malignancy.", "Skin lesion removed by dermatology in 2019; pathology report not available."]],
    evidence=[{"quote": "Skin lesion removed by dermatology in 2019; pathology report not available.", "concept": "procedure", "term": "skin lesion excision", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="cancer denial replaced by an excised skin lesion of unknown pathology",
    check_terms=["malignan", "cancer", "carcinoma"])
add(base="SYN-0006", variant="missing", criterion_id="NCT06786676-E15", doc_id="SYN-0006-D08",
    replace=[["Alcohol: 1 glass of wine 1-2 times per week. No substance use. ", ""]],
    action="patient_question", note="alcohol history and the substance-use denial removed; nothing else says whether she drinks",
    check_terms=["alcohol", "wine", "drink"])

# ---------------- SYN-0007 (alcohol-related acute pancreatitis)
add(base="SYN-0007", variant="violation", criterion_id="NCT06880770-E15", doc_id="SYN-0007-D08",
    replace=[["AST 58 U/L (10-40) H", "AST 128 U/L (10-40) H"]],
    evidence=[{"quote": "AST 128 U/L (10-40) H", "concept": "ast", "value": 128, "unit": "U/L"}],
    action="none", note="AST 128 U/L > 2.5 x ULN (100)", check_terms=["AST", "transaminase", "LFT"])
add(base="SYN-0007", variant="conflict", criterion_id="NCT07803965-E06", doc_id="NEW",
    new_doc={"type": "discharge_summary", "date": "2026-09-15", "author_role": "physician",
             "text": "Outside hospital records (requested at admission). 2022-05: right hemicolectomy for colon adenocarcinoma, pT2N0, no adjuvant therapy. Surveillance colonoscopy 2023 without recurrence."},
    evidence=[{"quote": "2022-05: right hemicolectomy for colon adenocarcinoma, pT2N0, no adjuvant therapy.", "concept": "diagnosis", "term": "colon adenocarcinoma", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="outside records report colon cancer resected in 2022 (within 5 years); the clinic note says no prior malignancy",
    check_terms=["malignan", "cancer", "colectomy", "adenocarcinoma"])

# ---------------- SYN-0008 (acute EBV mononucleosis)
add(base="SYN-0008", variant="violation", criterion_id="NCT06908096-I12", doc_id="SYN-0008-D07",
    replace=[["Platelets 188 x10^9/L (ref 150-400)", "Platelets 98 x10^9/L (ref 150-400) L"]],
    evidence=[{"quote": "Platelets 98 x10^9/L (ref 150-400) L", "concept": "platelet_count", "value": 98, "unit": "x10^9/L"}],
    action="none", note="platelets 98,000/uL < 125,000", check_terms=["platelet", "plt"])
add(base="SYN-0008", variant="conflict", criterion_id="NCT06908096-E16", doc_id="NEW",
    new_doc={"type": "clinic_note", "date": "2026-09-25", "author_role": "physician",
             "text": "Hematology clinic letter (outside). Classic Hodgkin lymphoma, nodular sclerosis, stage IIA diagnosed 2024-02; completed ABVD x4 in 2024-07. Last PET-CT 2026-02 equivocal residual mediastinal uptake; follow-up PET planned."},
    evidence=[{"quote": "Classic Hodgkin lymphoma, nodular sclerosis, stage IIA diagnosed 2024-02; completed ABVD x4 in 2024-07.", "concept": "diagnosis", "term": "Hodgkin lymphoma", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="outside hematology letter reports Hodgkin lymphoma treated in 2024 with equivocal residual uptake; the clinic note says no prior malignancy",
    check_terms=["malignan", "lymphoma", "cancer", "ABVD"])
add(base="SYN-0008", variant="unsupported", criterion_id="NCT06908096-E21", doc_id="SYN-0008-D07",
    replace=[["HIV-1/2 Ag/Ab: negative", "HIV-1/2 Ag/Ab: specimen sent to reference laboratory, result pending"]],
    evidence=[{"quote": "HIV-1/2 Ag/Ab: specimen sent to reference laboratory, result pending", "concept": "hiv", "value": None, "unit": None}],
    action="lab_check", note="HIV test ordered but the result is pending", check_terms=["HIV"])
# ---------------- SYN-0009 (metastatic colorectal cancer)
add(base="SYN-0009", variant="unsupported", criterion_id="NCT06244771-E03", doc_id="SYN-0009-D08",
    replace=[["ALLERGIES: NKDA.", "ALLERGIES: reports a 'reaction' during a chemotherapy infusion in 2025; agent and type of reaction not documented."]],
    evidence=[{"quote": "ALLERGIES: reports a 'reaction' during a chemotherapy infusion in 2025; agent and type of reaction not documented.", "concept": "allergy", "term": "chemotherapy infusion reaction", "value": None, "unit": None}],
    action="patient_question", note="NKDA replaced by an unidentified infusion reaction: hypersensitivity to the study drug cannot be ruled out or shown",
    check_terms=["NKDA", "allerg", "infusion reaction"])
add(base="SYN-0009", variant="missing", criterion_id="NCT04929223-E09", doc_id="SYN-0009-D08",
    replace=[["with no abdominal pain, no change in bowel habit", "with no change in bowel habit"]],
    action="patient_question", note="pain denial removed; nothing else says whether tumor pain is present or controlled",
    check_terms=["pain", "analges", "opioid"])

# ---------------- SYN-0010 (rheumatoid arthritis)
add(base="SYN-0010", variant="violation", criterion_id="NCT07409103-I03", doc_id="SYN-0010-D07",
    replace=[["Weight 68 kg. BMI 25.0 kg/m2.", "Weight 92 kg. BMI 33.8 kg/m2."]],
    evidence=[{"quote": "BMI 33.8 kg/m2.", "concept": "bmi", "value": 33.8, "unit": "kg/m2"}],
    action="none", note="BMI 33.8 > 32.0", check_terms=["BMI", "weight", " kg"])
add(base="SYN-0010", variant="conflict", criterion_id="NCT05428488-E23", doc_id="NEW",
    new_doc={"type": "lab_result", "date": "2026-09-10", "author_role": "lab",
             "text": "Outside laboratory report (same-day sample sent by the referring clinic). HBsAg reactive. Anti-HBc total reactive. HBV DNA not performed."},
    evidence=[{"quote": "HBsAg reactive.", "concept": "hepatitis_b", "value": "reactive", "unit": None}],
    action="clinician_confirmation", note="outside lab on the same day reports HBsAg reactive; the clinic lab reports HBsAg and anti-HBc negative",
    check_terms=["HBsAg", "hepatitis B", "anti-HBc"])
# ---------------- SYN-0011 (stage IV lung adenocarcinoma)
add(base="SYN-0011", variant="conflict", criterion_id="NCT06692738-E07", doc_id="NEW",
    new_doc={"type": "clinic_note", "date": "2026-09-20", "author_role": "physician",
             "text": "Rheumatology letter (outside). Seropositive rheumatoid arthritis since 2018, on methotrexate 15 mg weekly with folic acid; last visit 2026-08, disease in low activity."},
    evidence=[{"quote": "Seropositive rheumatoid arthritis since 2018, on methotrexate 15 mg weekly with folic acid", "concept": "diagnosis", "term": "rheumatoid arthritis", "value": True, "unit": None, "status": "current"}],
    action="clinician_confirmation", note="outside rheumatology letter reports RA on methotrexate; the oncology note says no autoimmune history and no immunosuppressants",
    check_terms=["rheumat", "methotrexate", "autoimmune"])

# ---------------- SYN-0012 (type 2 diabetes)
add(base="SYN-0012", variant="conflict", criterion_id="NCT07379333-E19", doc_id="NEW",
    new_doc={"type": "discharge_summary", "date": "2025-11-14", "author_role": "physician",
             "text": "Emergency department summary (outside). Presented with acute alcohol intoxication after a fall. History of alcohol use disorder per family; referred to addiction services."},
    evidence=[{"quote": "History of alcohol use disorder per family; referred to addiction services.", "concept": "alcohol", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="outside ED summary reports alcohol use disorder; the clinic notes record light drinking only",
    check_terms=["alcohol", "drinks", "substance"])
add(base="SYN-0012", variant="unsupported", criterion_id="NCT07365358-E06", doc_id="SYN-0012-D07",
    replace=[["No OTC supplements, no steroids.", "No OTC supplements. Received an injection for a knee flare at an urgent care clinic on 2026-09-10; product not recorded."]],
    evidence=[{"quote": "Received an injection for a knee flare at an urgent care clinic on 2026-09-10; product not recorded.", "concept": "medication", "term": "injection for knee flare", "value": True, "unit": None}],
    action="med_history_check", note="steroid denial replaced by an unidentified joint injection 3 weeks ago (possibly a corticosteroid)",
    check_terms=["steroid", "prednis", "injection"])

# ---------------- SYN-0013 (COPD GOLD 3)
add(base="SYN-0013", variant="violation", criterion_id="NCT07190222-I09", doc_id="SYN-0013-D08",
    replace=[["Wt 72 kg. BMI 23.5 kg/m2.", "Wt 126 kg. BMI 41.1 kg/m2."]],
    evidence=[{"quote": "BMI 41.1 kg/m2.", "concept": "bmi", "value": 41.1, "unit": "kg/m2"}],
    action="none", note="BMI 41.1 > 40.0", check_terms=["BMI", "weight", "Wt "])
add(base="SYN-0013", variant="conflict", criterion_id="NCT07053423-E04", doc_id="NEW",
    new_doc={"type": "clinic_note", "date": "2026-08-12", "author_role": "physician",
             "text": "Outside pulmonology letter. Alpha-1 antitrypsin deficiency, PiMZ genotype on testing in 2019; augmentation therapy not indicated. Advised smoking abstinence."},
    evidence=[{"quote": "Alpha-1 antitrypsin deficiency, PiMZ genotype on testing in 2019", "concept": "diagnosis", "term": "alpha-1 antitrypsin deficiency", "value": True, "unit": None, "status": "past"}],
    action="clinician_confirmation", note="outside letter reports A1AT deficiency (PiMZ); the lab shows a normal A1AT level",
    check_terms=["antitrypsin", "A1AT", "AATD"])
add(base="SYN-0013", variant="unsupported", criterion_id="NCT07053423-E04", doc_id="SYN-0013-D09",
    replace=[["Alpha-1 antitrypsin 135 mg/dL (ref 90-200)", "Alpha-1 antitrypsin: sent to reference laboratory, result pending"]],
    evidence=[{"quote": "Alpha-1 antitrypsin: sent to reference laboratory, result pending", "concept": "lab_other", "term": "alpha-1 antitrypsin", "value": None, "unit": None}],
    action="lab_check", note="A1AT level ordered but pending", check_terms=["antitrypsin", "A1AT"])

# ---------------- SYN-0015 (episodic migraine)
add(base="SYN-0015", variant="conflict", criterion_id="NCT03404336-E01", doc_id="NEW",
    new_doc={"type": "clinic_note", "date": "2026-09-12", "author_role": "physician",
             "text": "GP note. Headache diary reviewed: simple analgesics on 18 days/month and triptan on 11 days/month for the last 3 months. Assessment: medication overuse headache (ICHD-3 criteria met). Advised withdrawal of analgesics."},
    evidence=[{"quote": "Assessment: medication overuse headache (ICHD-3 criteria met).", "concept": "diagnosis", "term": "medication overuse headache", "value": True, "unit": None, "status": "current"}],
    action="clinician_confirmation", note="GP diary review 2 weeks earlier counts analgesic days in the overuse range; the neurology note says below the overuse range",
    check_terms=["overuse", "analgesic", "triptan"])
# ---------------- SYN-0016 (heart failure)
add(base="SYN-0016", variant="missing", criterion_id="NCT06979375-E08", doc_id="SYN-0016-D08",
    replace=[["AST 26 U/L (10-40)\nALT 24 U/L (7-56)\n", ""]],
    action="lab_check", note="AST and ALT removed from the screening panel", check_terms=["AST", "ALT", "LFT", "liver"])

# ---------------- SYN-0018 (IPF)
add(base="SYN-0018", variant="conflict", criterion_id="NCT06747923-E08", doc_id="NEW",
    new_doc={"type": "imaging_report", "date": "2026-09-12", "author_role": "physician",
             "text": "Outside echocardiogram (referring hospital) 2026-09-12: RV mildly dilated, TAPSE 17 mm, estimated RVSP 54 mmHg. Impression: moderate pulmonary hypertension."},
    evidence=[{"quote": "Impression: moderate pulmonary hypertension.", "concept": "diagnosis", "term": "pulmonary hypertension", "value": True, "unit": None, "status": "current"}],
    action="clinician_confirmation", note="two echocardiograms in September disagree: outside RVSP 54 mmHg with PH vs ours RVSP 32 mmHg without PH",
    check_terms=["pulmonary hypertension", "RVSP", "PAP"])
add(base="SYN-0018", variant="unsupported", criterion_id="NCT06747923-E10", doc_id="SYN-0018-D10",
    replace=[["HBsAg negative\nAnti-HBc total negative\nAnti-HCV negative\nHIV-1/2 Ag/Ab negative", "Hepatitis B, hepatitis C and HIV screening ordered; specimens sent, results pending"]],
    evidence=[{"quote": "Hepatitis B, hepatitis C and HIV screening ordered; specimens sent, results pending", "concept": "hiv", "value": None, "unit": None}],
    action="lab_check", note="HIV/HBV/HCV screening ordered but pending", check_terms=["HIV", "HBsAg", "HCV", "hepatitis"])

# ---------------- SYN-0020 (Graves disease)
add(base="SYN-0020", variant="violation", criterion_id="NCT07762105-E10", doc_id="SYN-0020-D09",
    replace=[["Creatinine 0.62 mg/dL (0.50-1.00)", "Creatinine 2.41 mg/dL (0.50-1.00) H"], ["eGFR 125 mL/min/1.73m2 (>90)", "eGFR 26 mL/min/1.73m2 (>90) L"]],
    evidence=[{"quote": "eGFR 26 mL/min/1.73m2 (>90) L", "concept": "egfr", "value": 26, "unit": "mL/min/1.73m2"}],
    action="none", note="eGFR 26 < 30", check_terms=["eGFR", "creatinine", "renal", "kidney"])
add(base="SYN-0020", variant="conflict", criterion_id="NCT07762105-E02", doc_id="NEW",
    new_doc={"type": "clinic_note", "date": "2026-09-15", "author_role": "physician",
             "text": "Rheumatology letter (outside). Systemic lupus erythematosus diagnosed 2023 (malar rash, arthritis, ANA 1:640, anti-dsDNA positive). On hydroxychloroquine 200 mg daily and azathioprine 100 mg daily."},
    evidence=[{"quote": "On hydroxychloroquine 200 mg daily and azathioprine 100 mg daily.", "concept": "medication", "term": "azathioprine", "value": True, "unit": None, "status": "current"}],
    action="clinician_confirmation", note="outside rheumatology letter reports SLE on azathioprine; the clinic note says no other autoimmune history",
    check_terms=["lupus", "azathioprine", "autoimmune", "rheumat"])
add(base="SYN-0020", variant="unsupported", criterion_id="NCT07762105-E01", doc_id="SYN-0020-D08",
    replace=[["no visual change.", "intermittent blurred vision over the past week, not yet examined by ophthalmology."]],
    evidence=[{"quote": "intermittent blurred vision over the past week, not yet examined by ophthalmology.", "concept": "symptom_finding", "term": "blurred vision", "value": True, "unit": None, "status": "current"}],
    action="clinician_confirmation", note="new blurred vision without an eye exam: optic neuropathy cannot be ruled out or shown",
    check_terms=["visual", "vision", "optic", "cornea"])
add(base="SYN-0020", variant="missing", criterion_id="NCT07762105-E03", doc_id="SYN-0020-D08",
    replace=[["ALLERGIES: NKDA.\n", ""]],
    action="patient_question", note="allergy history removed; nothing else says whether she is allergic to statins",
    check_terms=["NKDA", "allerg", "statin"])

json.dump(E, open("edits_dev.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(E), "edits")
