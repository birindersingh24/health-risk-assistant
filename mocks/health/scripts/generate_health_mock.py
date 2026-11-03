#!/usr/bin/env python3
"""
Mock patient records for a chronic-disease Health Risk Assistant, with planted
findings and a ground-truth answer key.

    python scripts/generate_health_mock.py               # as of 2026-11-01, 51 patients, seed 42
    python scripts/generate_health_mock.py --as-of 2027-03-01 --seed 7 --out /tmp/health

Writes (under --out, default mocks/health/):
    data/tables/patients.csv        one row per patient
    data/tables/observations.csv    vitals and labs with LOINC codes, seven visits over three years
    data/tables/conditions.csv      problem list with ICD-10-CM codes
    data/tables/medications.csv     current and past prescriptions
    evals/cases.json                answer key: what was planted, in which patient, and how to detect it

Standard library only. Every patient, clinician and record is fictional, except P051:
a real record shared by its owner for testing (see data/corpus/notes/P051.md).
Thresholds follow the mock protocols in data/corpus/guidelines/, not real clinical guidance.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

N_PATIENTS = 51
VISIT_MONTHS_AGO = [36, 30, 24, 18, 12, 6, 0]   # seven visits, about six months apart
CASE_VISIT_GAP = 10                             # planted patients get fixed visit dates so the notes can match them

LOINC = {
    "sbp":   ("8480-6", "Systolic blood pressure", "mm[Hg]"),
    "dbp":   ("8462-4", "Diastolic blood pressure", "mm[Hg]"),
    "bmi":   ("39156-5", "Body mass index", "kg/m2"),
    "hba1c": ("4548-4", "Hemoglobin A1c", "%"),
    "fg":    ("1558-6", "Fasting glucose", "mg/dL"),
    "tc":    ("2093-3", "Total cholesterol", "mg/dL"),
    "hdl":   ("2085-9", "HDL cholesterol", "mg/dL"),
    "ldl":   ("13457-7", "LDL cholesterol (calculated)", "mg/dL"),
    "egfr":  ("98979-8", "eGFR (CKD-EPI 2021)", "mL/min/1.73m2"),
    "acr":   ("9318-7", "Urine albumin/creatinine ratio", "mg/g"),
}

CONDITIONS = {
    "htn":            ("I10", "Essential (primary) hypertension"),
    "t2d":            ("E11.9", "Type 2 diabetes mellitus without complications"),
    "prediabetes":    ("R73.03", "Prediabetes"),
    "hyperlipidemia": ("E78.5", "Hyperlipidemia, unspecified"),
    "obesity":        ("E66.9", "Obesity, unspecified"),
    "ckd3a":          ("N18.31", "Chronic kidney disease, stage 3a"),
    "acl_left":       ("S83.512A", "Sprain of anterior cruciate ligament of left knee, initial encounter"),
}

DRUG_CLASS = {
    "lisinopril": "ace_inhibitor", "losartan": "arb", "amlodipine": "ccb",
    "hydrochlorothiazide": "thiazide", "atorvastatin": "statin", "rosuvastatin": "statin",
    "metformin": "biguanide",
}
BP_CLASSES = {"ace_inhibitor", "arb", "ccb", "thiazide"}

CLINICIANS = ["Dr. Mira Okafor", "Dr. Tomas Lindqvist", "Dr. Priya Raman", "NP Jordan Ellis"]
FIRST = {
    "female": ["Ana", "Beatriz", "Chloe", "Dana", "Elif", "Fatima", "Grace", "Hana", "Ines", "June",
               "Keiko", "Lena", "Maya", "Nora", "Olga", "Rosa", "Sana", "Tess", "Vera", "Yara"],
    "male":   ["Aaron", "Bilal", "Carlos", "Dmitri", "Eitan", "Felix", "Gabe", "Hiro", "Ivan", "Jonas",
               "Kofi", "Luca", "Marek", "Nikhil", "Omar", "Pavel", "Rafael", "Sami", "Theo", "Viktor"],
}
LAST = ["Abara", "Bergstrom", "Castellano", "Dubois", "Eriksen", "Fontaine", "Gallo", "Haddad", "Iwata",
        "Jovanovic", "Kowalczyk", "Lindahl", "Moreau", "Nakamura", "Oyelaran", "Petrakis", "Quintero",
        "Rossetti", "Sandoval", "Takahashi", "Uribe", "Varga", "Whitlock", "Yilmaz", "Zielinski"]


# ---------------------------------------------------------------- risk score
def risk_points(age, sex, smoker, diabetes, sbp, on_bp_treatment, tc, hdl, family_history) -> int:
    """Example Clinic Cardiovascular Risk Points, the teaching score in data/corpus/guidelines/risk-01.md."""
    pts = 0 if age < 40 else 2 if age < 50 else 4 if age < 60 else 6 if age < 70 else 8
    pts += sex == "male"
    pts += 3 * bool(smoker) + 3 * bool(diabetes)
    pts += 0 if sbp < 120 else 1 if sbp < 140 else 2 if sbp < 160 else 3
    pts += bool(on_bp_treatment)
    ratio = tc / hdl
    pts += 0 if ratio < 4 else 1 if ratio < 6 else 2
    pts += bool(family_history)
    return pts


def risk_band(pts: int) -> str:
    return "low" if pts <= 5 else "borderline" if pts <= 8 else "intermediate" if pts <= 11 else "high"


# ---------------------------------------------------------------- model
@dataclass
class Patient:
    pid: str
    birth: date
    sex: str
    smoking: str                    # never | former | current
    family_history: bool            # premature ASCVD in a first-degree relative, as structured data
    bp: list                        # (systolic, diastolic) per visit
    bmi: float
    labs: dict = field(default_factory=dict)        # key -> {visit index or date: value}; "lipid" -> (tc, hdl, ldl)
    conditions: list = field(default_factory=list)  # (condition key, onset, status)
    meds: list = field(default_factory=list)        # (drug, strength_mg, times_per_day, start, end or None)
    visits: list = field(default_factory=list)
    name: tuple | None = None       # (given, family); None draws a fictional name


def years_ago(as_of: date, years: float) -> date:
    return as_of - timedelta(days=round(years * 365.25))


def born(as_of: date, age: int, extra_days: int) -> date:
    """A birth date that makes the patient exactly `age` on as_of (extra_days < 365)."""
    try:
        return as_of.replace(year=as_of.year - age) - timedelta(days=extra_days)
    except ValueError:                                  # as_of is Feb 29
        return date(as_of.year - age, 2, 28) - timedelta(days=extra_days)


def age_on(birth: date, d: date) -> int:
    return d.year - birth.year - ((d.month, d.day) < (birth.month, birth.day))


def visit_dates(as_of: date, gaps: list) -> list:
    return [as_of - timedelta(days=round(m * 30.44) + g) for m, g in zip(VISIT_MONTHS_AGO, gaps)]


def latest(series: dict, visits: list):
    """Most recent value of a {visit index or date: value} series."""
    dated = sorted((visits[k] if isinstance(k, int) else k, v) for k, v in series.items())
    return dated[-1] if dated else (None, None)


def active_meds(p: Patient, on: date) -> list:
    return [m for m in p.meds if m[3] <= on and (m[4] is None or m[4] > on)]


def risk_inputs(p: Patient, as_of: date) -> dict:
    _, (tc, hdl, _) = latest(p.labs["lipid"], p.visits)
    classes = {DRUG_CLASS[m[0]] for m in active_meds(p, as_of)}
    return dict(
        age=age_on(p.birth, as_of), sex=p.sex, smoker=p.smoking == "current",
        diabetes=any(c[0] == "t2d" and c[2] == "active" for c in p.conditions),
        sbp=p.bp[-1][0], on_bp_treatment=bool(classes & BP_CLASSES),
        tc=tc, hdl=hdl, family_history=p.family_history,
    )


# ---------------------------------------------------------------- planted cases
def planted(as_of: date) -> list:
    """(case metadata, Patient) for every planted finding. Values are explicit so each case is exact."""
    ago = lambda y: years_ago(as_of, y)
    flat = lambda s, d: [(s, d)] * 7
    cases = []

    def add(meta, p):
        cases.append((meta, p))

    add(dict(id="C01", type="healthy_control", detected_by=[], expected_doc_ids=["scr-01"],
             story="Young adult with normal values at every visit. Nothing should be flagged.",
             signal="No rule fires; the assistant should say no risk findings and name the next routine checks."),
        Patient("P003", born(as_of, 34, 230), "female", "never", False,
                [(112, 72), (110, 70), (114, 74), (108, 68), (112, 71), (110, 70), (113, 72)], 22.4,
                labs={"hba1c": {1: 5.1, 5: 5.2}, "fg": {1: 84, 5: 86},
                      "lipid": {1: (178, 62, 96), 5: (182, 64, 98)},
                      "egfr": {0: 104, 2: 102, 4: 101, 6: 103}}))

    add(dict(id="C02", type="undiagnosed_diabetes", detected_by=["undiagnosed_diabetes"],
             expected_doc_ids=["dm-01", "dq-01", "ops-01"],
             story="HbA1c climbed from normal through prediabetes to two results in the diabetes range. "
                   "Diabetes was never added to the problem list and no treatment started.",
             signal="Two or more HbA1c >= 6.5% with no active E11 diagnosis."),
        Patient("P007", born(as_of, 52, 160), "female", "never", False,
                [(122, 78), (124, 79), (121, 77), (125, 78), (124, 79), (123, 78), (124, 78)], 29.4,
                labs={"hba1c": {0: 5.6, 2: 5.9, 4: 6.2, 5: 6.6, 6: 6.8},
                      "fg": {0: 98, 2: 104, 4: 115, 5: 128, 6: 134},
                      "lipid": {1: (196, 52, 118), 5: (204, 51, 124)},
                      "egfr": {0: 96, 2: 95, 4: 93, 6: 92}}))

    add(dict(id="C03", type="resistant_hypertension", detected_by=["resistant_hypertension"],
             expected_doc_ids=["htn-02", "htn-01", "ops-01"],
             story="Blood pressure stays around 150/94 on three drugs from different classes, including a "
                   "thiazide diuretic. The notes confirm he takes them every day.",
             signal="Three or more active BP drug classes and the mean of the last three readings >= 140/90."),
        Patient("P012", born(as_of, 59, 85), "male", "never", False,
                [(154, 96), (150, 94), (156, 95), (149, 92), (152, 94), (148, 92), (155, 96)], 31.2,
                labs={"hba1c": {1: 5.4, 5: 5.5}, "fg": {1: 92, 5: 94},
                      "lipid": {1: (188, 44, 112), 5: (176, 45, 104)},
                      "egfr": {0: 82, 2: 80, 4: 79, 6: 78}, "acr": {2: 18, 6: 22}},
                conditions=[("htn", ago(10.5), "active"), ("hyperlipidemia", ago(5.6), "active"),
                            ("obesity", ago(4), "active")],
                meds=[("lisinopril", 40, 1, ago(8.2), None), ("amlodipine", 10, 1, ago(6.1), None),
                      ("hydrochlorothiazide", 25, 1, ago(4.2), None), ("atorvastatin", 20, 1, ago(5.6), None)]))

    add(dict(id="C04", type="prediabetes_borderline", detected_by=["prediabetes"],
             expected_doc_ids=["dm-01", "dm-02", "htn-01"],
             story="Latest HbA1c is exactly 6.4% and latest BP exactly 129/79. Both sit one step below the "
                   "next category, to catch off-by-one thresholds.",
             signal="Prediabetes (5.7-6.4%), not diabetes. BP is 'elevated', not stage 1 hypertension."),
        Patient("P015", born(as_of, 48, 270), "male", "never", False,
                [(126, 78), (128, 79), (127, 78), (129, 79), (128, 78), (127, 79), (129, 79)], 28.1,
                labs={"hba1c": {0: 5.8, 2: 5.9, 4: 6.1, 6: 6.4}, "fg": {0: 104, 2: 108, 4: 110, 6: 112},
                      "lipid": {1: (192, 47, 120), 5: (198, 48, 124)},
                      "egfr": {0: 98, 2: 97, 4: 96, 6: 96}},
                conditions=[("prediabetes", ago(2.9), "active")]))

    add(dict(id="C05", type="statin_gap", detected_by=["statin_gap"],
             expected_doc_ids=["risk-01", "lip-01"],
             story="Current smoker in his sixties on treatment for hypertension. His risk score is in the high "
                   "band and he has never been offered a statin.",
             signal="Risk band 'high' and no active statin."),
        Patient("P018", born(as_of, 64, 300), "male", "current", False,
                [(136, 84), (138, 85), (134, 82), (137, 84), (139, 86), (136, 83), (138, 84)], 27.0,
                labs={"hba1c": {1: 5.5, 5: 5.5}, "fg": {1: 95, 5: 94},
                      "lipid": {1: (226, 40, 150), 5: (220, 40, 146)},
                      "egfr": {0: 84, 2: 82, 4: 81, 6: 80}, "acr": {2: 12, 6: 14}},
                conditions=[("htn", ago(7.2), "active")],
                meds=[("lisinopril", 20, 1, ago(7.1), None)]))

    add(dict(id="C06", type="metformin_renal_dose", detected_by=["metformin_renal"],
             expected_doc_ids=["ckd-02", "ckd-01", "ops-01"],
             story="Kidney function fell steadily from 64 to 38 over three years. She is still on the full "
                   "2000 mg/day of metformin. CKD is on the problem list, but as stage 3a, from an older result.",
             signal="Active metformin above 1000 mg/day while latest eGFR is below 45."),
        Patient("P021", born(as_of, 71, 60), "female", "former", False,
                [(128, 76), (126, 74), (130, 77), (127, 75), (129, 76), (128, 75), (128, 76)], 30.6,
                labs={"hba1c": {i: v for i, v in enumerate([7.1, 7.0, 7.2, 7.3, 7.1, 7.2, 7.3])},
                      "fg": {i: v for i, v in enumerate([134, 132, 138, 140, 133, 136, 139])},
                      "lipid": {1: (168, 52, 88), 5: (164, 54, 84)},
                      "egfr": {i: v for i, v in enumerate([64, 61, 57, 52, 47, 42, 38])},
                      "acr": {2: 42, 4: 55, 6: 68}},
                conditions=[("t2d", ago(11.7), "active"), ("htn", ago(9.4), "active"),
                            ("ckd3a", ago(1.4), "active"), ("obesity", ago(6), "active")],
                meds=[("metformin", 1000, 2, ago(11.6), None), ("lisinopril", 10, 1, ago(9.4), None),
                      ("atorvastatin", 40, 1, ago(11.6), None)]))

    add(dict(id="C07", type="lipid_panel_overdue", detected_by=["lipid_overdue"],
             expected_doc_ids=["lip-01", "scr-01"],
             story="Treated hypertension, seen every six months, but his only lipid panel is about 6.5 years "
                   "old. His risk score therefore rests on stale cholesterol values.",
             signal="No lipid panel in the last 5 years."),
        Patient("P026", born(as_of, 54, 345), "male", "former", False,
                [(124, 78), (122, 77), (126, 79), (123, 78), (125, 78), (122, 76), (124, 78)], 27.8,
                labs={"hba1c": {1: 5.3, 5: 5.4}, "fg": {1: 90, 5: 91},
                      "lipid": {years_ago(as_of, 6.5): (214, 46, 140)},
                      "egfr": {0: 92, 2: 91, 4: 90, 6: 89}, "acr": {2: 10, 6: 12}},
                conditions=[("htn", ago(7.2), "active")],
                meds=[("losartan", 50, 1, ago(7.1), None)]))

    add(dict(id="C08", type="conflicting_diagnosis", detected_by=["conflicting_diagnosis"],
             expected_doc_ids=["dq-01", "dm-01"],
             story="Type 2 diabetes is on the problem list, but every HbA1c and fasting glucose is normal and "
                   "she takes no diabetes medicine. The notes say the code came from an outside record.",
             signal="Active E11 diagnosis, every HbA1c < 5.7% and no diabetes medication."),
        Patient("P029", born(as_of, 45, 200), "female", "never", False,
                [(114, 72), (116, 74), (112, 70), (115, 73), (114, 72), (113, 71), (115, 72)], 24.3,
                labs={"hba1c": {0: 5.3, 2: 5.2, 4: 5.4, 6: 5.3}, "fg": {0: 88, 2: 86, 4: 91, 6: 89},
                      "lipid": {1: (172, 66, 90), 5: (176, 64, 94)},
                      "egfr": {0: 101, 2: 100, 4: 99, 6: 100}},
                conditions=[("t2d", ago(4.6), "active")]))

    add(dict(id="C09", type="statin_declined", detected_by=["statin_gap"],
             expected_doc_ids=["risk-01", "lip-01", "ops-02"],
             story="High risk band and no statin, so the rule flags her exactly like P018. The notes record "
                   "that she declined a statin twice. That is a documented decision, not an unnoticed gap.",
             signal="Same structured signal as C05; the difference is only in the notes (data/corpus/notes/P033.md).",
             notes_only_fact="Declined statin on two visits after discussion of risk."),
        Patient("P033", born(as_of, 68, 40), "female", "current", False,
                [(136, 82), (134, 80), (138, 84), (135, 81), (137, 83), (134, 80), (136, 82)], 26.5,
                labs={"hba1c": {1: 5.5, 5: 5.5}, "fg": {1: 93, 5: 95},
                      "lipid": {1: (238, 45, 160), 5: (242, 44, 164)},
                      "egfr": {0: 80, 2: 79, 4: 78, 6: 77}, "acr": {2: 9, 6: 11}},
                conditions=[("htn", ago(8.3), "active")],
                meds=[("amlodipine", 5, 1, ago(8.2), None)]))

    add(dict(id="C10", type="ckd_unrecorded", detected_by=["ckd_unrecorded"],
             expected_doc_ids=["ckd-01", "dq-01"],
             story="eGFR has been between 52 and 58 for over two years and urine albumin is moderately raised, "
                   "which meets the CKD definition (G3a A2). CKD is not on the problem list.",
             signal="eGFR < 60 on results at least 90 days apart, with no active N18 diagnosis."),
        Patient("P040", born(as_of, 66, 120), "male", "never", False,
                [(126, 78), (128, 79), (124, 77), (127, 78), (126, 77), (125, 78), (126, 78)], 28.4,
                labs={"hba1c": {1: 5.4, 5: 5.4}, "fg": {1: 92, 5: 93},
                      "lipid": {1: (198, 48, 120), 5: (194, 49, 118)},
                      "egfr": {i: v for i, v in enumerate([63, 58, 57, 56, 55, 53, 52])},
                      "acr": {2: 38, 4: 44, 6: 48}},
                conditions=[("htn", ago(12.1), "active")],
                meds=[("amlodipine", 5, 1, ago(12.0), None)]))

    add(dict(id="C11", type="severe_bp", detected_by=["severe_bp"],
             expected_doc_ids=["htn-03", "ops-01"],
             story="Well-controlled hypertension until the latest visit, which read 186/122. The note says she ran "
                   "out of lisinopril five days earlier and has no symptoms, so this is urgency, not emergency.",
             signal="Latest systolic >= 180 or diastolic >= 120.",
             notes_only_fact="No symptoms of target-organ damage; missed lisinopril for 5 days."),
        Patient("P044", born(as_of, 61, 330), "female", "never", False,
                [(132, 84), (130, 82), (134, 85), (131, 83), (133, 84), (130, 82), (186, 122)], 29.0,
                labs={"hba1c": {1: 5.4, 5: 5.4}, "fg": {1: 90, 5: 92},
                      "lipid": {1: (204, 47, 128), 5: (208, 47, 130)},
                      "egfr": {0: 86, 2: 85, 4: 85, 6: 84}, "acr": {2: 14, 6: 15}},
                conditions=[("htn", ago(6.3), "active")],
                meds=[("lisinopril", 20, 1, ago(6.2), None)]))

    add(dict(id="C12", type="family_history_in_notes", detected_by=[],
             expected_doc_ids=["risk-01", "lip-01"],
             story="Structured data scores 11 points (intermediate). His notes record that his father had a heart "
                   "attack at 48, which adds 1 point and moves him to the high band. No rule can see this.",
             signal="Only found by reading the notes (data/corpus/notes/P047.md) and recalculating the score.",
             notes_only_fact="Father had a myocardial infarction at age 48."),
        Patient("P047", born(as_of, 61, 220), "male", "former", False,
                [(144, 88), (142, 86), (146, 89), (143, 87), (145, 88), (142, 86), (144, 88)], 29.6,
                labs={"hba1c": {1: 5.5, 5: 5.5}, "fg": {1: 94, 5: 96},
                      "lipid": {1: (214, 44, 140), 5: (216, 45, 142)},
                      "egfr": {0: 88, 2: 87, 4: 86, 6: 86}, "acr": {2: 16, 6: 18}},
                conditions=[("htn", ago(5.4), "active")],
                meds=[("losartan", 50, 1, ago(5.3), None)]))

    add(dict(id="C13", type="out_of_scope_orthopedic", detected_by=["lipid_overdue"],
             expected_doc_ids=["scr-01", "lip-01"],
             story="A real record, shared by the patient for testing. A young adult recovering from left ACL "
                   "reconstruction; every note is orthopaedic. The clinic holds no vitals, labs or prescriptions "
                   "for him, and smoking status and family history are not recorded.",
             signal="No lipid panel on record, so lipid_overdue fires. No risk score can be computed. Knee, "
                    "rehab and NSAID questions are outside the protocols."),
        Patient("P051", born(as_of, 29, 120), "male", None, None, [], None,
                conditions=[("acl_left", date(2026, 7, 15), "active")], name=("Gurjeet", "Singh")))

    for _, p in cases:
        gaps = [CASE_VISIT_GAP] * 7
        if p.pid == "P044":
            gaps[-1] = 4                       # the severe reading is the most recent visit
        p.visits = visit_dates(as_of, gaps)
    return cases


# ---------------------------------------------------------------- background patients
def background(pid: str, rng: random.Random, as_of: date) -> Patient:
    """An unremarkable patient. Values stay clear of every rule threshold."""
    kind = rng.choices(["healthy", "htn", "t2d", "lipids"], [40, 25, 20, 15])[0]
    age = rng.randint(28, 70) if kind == "healthy" else rng.randint(45, 77)
    sex = rng.choice(["female", "male"])
    ago = lambda y: years_ago(as_of, y)
    j = lambda base, d: base + rng.randint(-d, d)

    sys_base, dia_base = (rng.randint(106, 118), rng.randint(66, 76)) if kind == "healthy" \
        else (rng.randint(116, 124), rng.randint(70, 77))
    p = Patient(
        pid, born(as_of, age, rng.randint(0, 364)), sex,
        rng.choices(["never", "former", "current"], [60, 28, 12])[0], rng.random() < 0.12,
        [(j(sys_base, 4), j(dia_base, 3)) for _ in range(7)], round(rng.uniform(20.5, 33.5), 1),
        visits=visit_dates(as_of, [rng.randint(3, 25) for _ in range(7)]),
    )

    statin = kind in ("t2d", "lipids")
    tc, hdl = (rng.randint(150, 190) if statin else rng.randint(165, 225)), rng.randint(40, 70)
    p.labs["lipid"] = {k: (j(tc, 6), hdl, j(tc, 6) - hdl - rng.randint(18, 32)) for k in (1, 5)}
    egfr = max(72, round(105 - 0.5 * (age - 30) + rng.randint(-6, 6)))
    p.labs["egfr"] = {k: egfr - k // 2 for k in (0, 2, 4, 6)}
    if kind == "t2d":
        a1c, fg = rng.uniform(6.8, 7.2), rng.randint(125, 145)
        p.labs["hba1c"] = {k: round(a1c + rng.uniform(-0.2, 0.2), 1) for k in range(7)}
        p.labs["fg"] = {k: j(fg, 6) for k in range(7)}
    else:
        a1c, fg = rng.uniform(5.0, 5.4), rng.randint(80, 94)
        p.labs["hba1c"] = {k: round(a1c + rng.uniform(-0.1, 0.1), 1) for k in (1, 5)}
        p.labs["fg"] = {k: j(fg, 3) for k in (1, 5)}
    if kind in ("htn", "t2d"):
        p.labs["acr"] = {k: rng.randint(4, 24) for k in (2, 6)}

    if kind == "htn" or (kind == "t2d" and rng.random() < 0.4):
        onset = ago(rng.uniform(2, 12))
        p.conditions.append(("htn", onset, "active"))
        drug, mg = rng.choice([("lisinopril", 10), ("lisinopril", 20), ("losartan", 50), ("amlodipine", 5)])
        if drug == "losartan" and rng.random() < 0.4:      # switched from an ACE inhibitor (cough)
            p.meds.append(("lisinopril", 10, 1, onset + timedelta(days=30), onset + timedelta(days=400)))
            p.meds.append(("losartan", 50, 1, onset + timedelta(days=400), None))
        else:
            p.meds.append((drug, mg, 1, onset + timedelta(days=30), None))
            if drug != "amlodipine" and rng.random() < 0.15:
                p.meds.append(("amlodipine", 5, 1, onset + timedelta(days=500), None))
    if kind == "t2d":
        onset = ago(rng.uniform(2, 10))
        p.conditions.append(("t2d", onset, "active"))
        p.meds.append(("metformin", rng.choice([500, 1000]), 2, onset + timedelta(days=30), None))
        p.meds.append(("atorvastatin", 20, 1, onset + timedelta(days=60), None))
    if kind == "lipids":
        onset = ago(rng.uniform(1.5, 9))
        p.conditions.append(("hyperlipidemia", onset, "active"))
        drug, mg = rng.choice([("atorvastatin", 20), ("atorvastatin", 40), ("rosuvastatin", 10)])
        p.meds.append((drug, mg, 1, onset + timedelta(days=14), None))
    if p.bmi >= 30 and rng.random() < 0.7:                 # some obesity is left off the problem list
        p.conditions.append(("obesity", ago(rng.uniform(1, 6)), "active"))

    on_statin = any(DRUG_CLASS[m[0]] == "statin" for m in active_meds(p, as_of))
    if risk_band(risk_points(**risk_inputs(p, as_of))) == "high" and not on_statin:
        p.meds.append(("atorvastatin", 20, 1, ago(1.5), None))
    return p


# ---------------------------------------------------------------- output
def write_csv(path: Path, header: list, rows: list) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def generate(as_of: date, seed: int, out: Path) -> None:
    cases = planted(as_of)
    by_pid = {p.pid: p for _, p in cases}
    patients = [by_pid.get(f"P{n:03d}") or background(f"P{n:03d}", random.Random(f"{seed}:P{n:03d}"), as_of)
                for n in range(1, N_PATIENTS + 1)]

    name_rng = random.Random(f"{seed}:names")
    pat_rows, obs_rows, cond_rows, med_rows = [], [], [], []
    for p in patients:
        n = int(p.pid[1:])
        given, family = p.name or (name_rng.choice(FIRST[p.sex]), name_rng.choice(LAST))
        pat_rows.append([p.pid, given, family, p.birth.isoformat(), p.sex, p.smoking or "",   # "" = not recorded
                         "" if p.family_history is None else str(p.family_history).lower(),
                         CLINICIANS[n % len(CLINICIANS)]])

        obs = []
        for i, (s, d) in enumerate(p.bp):
            obs += [(p.visits[i], "sbp", s), (p.visits[i], "dbp", d),
                    (p.visits[i], "bmi", round(p.bmi + 0.1 * (i - 3) * (1 if p.pid == "P007" else 0.3), 1))]
        for key, series in p.labs.items():
            for k, v in series.items():
                d = p.visits[k] if isinstance(k, int) else k
                obs += [(d, "tc", v[0]), (d, "hdl", v[1]), (d, "ldl", v[2])] if key == "lipid" else [(d, key, v)]
        for d, key, v in sorted(obs, key=lambda o: (o[0], list(LOINC).index(o[1]))):
            code, display, unit = LOINC[key]
            obs_rows.append([p.pid, d.isoformat(), code, display, v, unit])

        for key, onset, status in p.conditions:
            code, display = CONDITIONS[key]
            cond_rows.append([p.pid, "ICD-10-CM", code, display, status, onset.isoformat()])
        for drug, mg, times, start, end in sorted(p.meds, key=lambda m: m[3]):
            med_rows.append([p.pid, drug, DRUG_CLASS[drug], mg, times, mg * times, start.isoformat(),
                             end.isoformat() if end else "", "stopped" if end and end <= as_of else "active"])

    (out / "data" / "tables").mkdir(parents=True, exist_ok=True)
    tables = out / "data" / "tables"          # what the assistant may read
    write_csv(tables / "patients.csv",
              ["patient_id", "given_name", "family_name", "birth_date", "sex", "smoking_status",
               "family_history_premature_ascvd", "primary_clinician"], pat_rows)
    write_csv(tables / "observations.csv",
              ["observation_id", "patient_id", "effective_date", "loinc_code", "display", "value", "unit"],
              [[f"OBS-{i:05d}"] + r for i, r in enumerate(obs_rows, 1)])
    write_csv(tables / "conditions.csv",
              ["condition_id", "patient_id", "code_system", "code", "display", "clinical_status", "onset_date"],
              [[f"COND-{i:04d}"] + r for i, r in enumerate(cond_rows, 1)])
    write_csv(tables / "medications.csv",
              ["medication_id", "patient_id", "drug", "drug_class", "strength_mg", "times_per_day",
               "daily_dose_mg", "start_date", "end_date", "status"],
              [[f"MED-{i:04d}"] + r for i, r in enumerate(med_rows, 1)])

    key = []
    for meta, p in cases:
        if not p.bp or "lipid" not in p.labs:              # too little data for a risk score
            facts = {"age": age_on(p.birth, as_of), "risk_points": None, "risk_band": None,
                     "not_recorded": ["blood pressure", "lipid panel", "smoking status", "family history"]}
            key.append({"id": meta.pop("id"), "type": meta.pop("type"), "patient_id": p.pid, **meta, "facts": facts})
            continue
        inputs = risk_inputs(p, as_of)
        pts = risk_points(**inputs)
        facts = {"age": inputs["age"], "risk_points": pts, "risk_band": risk_band(pts)}
        for lab in ("hba1c", "egfr"):
            d, v = latest(p.labs.get(lab, {}), p.visits)
            if v is not None:
                facts[f"latest_{lab}"] = {"value": v, "date": d.isoformat()}
        facts["latest_bp"] = {"value": "%d/%d" % p.bp[-1], "date": p.visits[-1].isoformat()}
        lipid_date, _ = latest(p.labs["lipid"], p.visits)
        facts["latest_lipid_panel"] = lipid_date.isoformat()
        if p.pid == "P047":
            facts["risk_points_with_notes"] = risk_points(**{**inputs, "family_history": True})
            facts["risk_band_with_notes"] = risk_band(facts["risk_points_with_notes"])
        key.append({"id": meta.pop("id"), "type": meta.pop("type"), "patient_id": p.pid, **meta, "facts": facts})
    (out / "evals").mkdir(exist_ok=True)       # answer key: test code only, never under data/
    (out / "evals" / "cases.json").write_text(json.dumps(key, indent=2) + "\n")

    print(f"{len(pat_rows)} patients, {len(obs_rows)} observations, {len(cond_rows)} conditions, "
          f"{len(med_rows)} medications, {len(key)} planted cases -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 1))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args()
    generate(a.as_of, a.seed, a.out)
