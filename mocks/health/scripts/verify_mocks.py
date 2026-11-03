#!/usr/bin/env python3
"""
Checks that the mock assets agree with each other.

    python scripts/verify_mocks.py      # exits 1 if any check fails

1. Each detection rule, run over the CSVs, finds exactly the patients evals/cases.json lists for it.
2. Every patient id and doc_id referenced in evals/ and the notes exists.
3. Every guideline has front matter and the mock banner; section sizes are reported.
4. Nothing under data/ leaks eval content: only .csv and .md files, and no answer-key wording.

The rules here are a reference for what is detectable from structured data, not the assistant's tools.
Standard library only.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TABLES, CORPUS, EVALS = ROOT / "data" / "tables", ROOT / "data" / "corpus", ROOT / "evals"
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True                 # keep __pycache__ out of the data folder
from generate_health_mock import BP_CLASSES, age_on, risk_band, risk_points  # noqa: E402

AS_OF = date(2026, 11, 1)
BANNER = "Mock document for a software demo"
failures = []


def check(ok: bool, msg: str) -> None:
    print(("  ok    " if ok else "  FAIL  ") + msg)
    if not ok:
        failures.append(msg)


def rows(name: str) -> list:
    with (TABLES / name).open() as f:
        return list(csv.DictReader(f))


def front_matter(path: Path) -> tuple:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines()) if m else {}
    return meta, text[m.end():] if m else text


# ---------------------------------------------------------------- load
patients = {r["patient_id"]: r for r in rows("patients.csv")}
obs = defaultdict(lambda: defaultdict(list))            # pid -> loinc -> [(date, value)]
for r in rows("observations.csv"):
    obs[r["patient_id"]][r["loinc_code"]].append((date.fromisoformat(r["effective_date"]), float(r["value"])))
for series in obs.values():
    for s in series.values():
        s.sort()
conds = defaultdict(list)
for r in rows("conditions.csv"):
    if r["clinical_status"] == "active":
        conds[r["patient_id"]].append(r["code"])
meds = defaultdict(list)
for r in rows("medications.csv"):
    if r["status"] == "active":
        meds[r["patient_id"]].append(r)
cases = json.loads((EVALS / "cases.json").read_text())

SBP, DBP, HBA1C, TC, HDL, EGFR = "8480-6", "8462-4", "4548-4", "2093-3", "2085-9", "98979-8"
has = lambda pid, prefix: any(c.startswith(prefix) for c in conds[pid])
classes = lambda pid: {m["drug_class"] for m in meds[pid]}


def score(pid: str) -> int | None:
    p = obs[pid]
    if not p[SBP] or not p[TC]:                 # no BP or lipid panel on record: no score
        return None
    return risk_points(
        age=age_on(date.fromisoformat(patients[pid]["birth_date"]), AS_OF), sex=patients[pid]["sex"],
        smoker=patients[pid]["smoking_status"] == "current", diabetes=has(pid, "E11"),
        sbp=p[SBP][-1][1], on_bp_treatment=bool(classes(pid) & BP_CLASSES),
        tc=p[TC][-1][1], hdl=p[HDL][-1][1],
        family_history=patients[pid]["family_history_premature_ascvd"] == "true")


def egfr_below_60_for_90_days(pid: str) -> bool:
    low = [d for d, v in obs[pid][EGFR] if v < 60]
    return bool(low) and obs[pid][EGFR][-1][1] < 60 and (low[-1] - low[0]).days >= 90


RULES = {
    "undiagnosed_diabetes": lambda pid: sum(v >= 6.5 for _, v in obs[pid][HBA1C]) >= 2 and not has(pid, "E11"),
    "prediabetes": lambda pid: bool(obs[pid][HBA1C]) and 5.7 <= obs[pid][HBA1C][-1][1] <= 6.4,
    "resistant_hypertension": lambda pid: len(classes(pid) & BP_CLASSES) >= 3 and (
        sum(v for _, v in obs[pid][SBP][-3:]) / 3 >= 140 or sum(v for _, v in obs[pid][DBP][-3:]) / 3 >= 90),
    "statin_gap": lambda pid: score(pid) is not None and risk_band(score(pid)) == "high" and "statin" not in classes(pid),
    "metformin_renal": lambda pid: any(
        m["drug"] == "metformin" and (int(m["daily_dose_mg"]) > 1000 and obs[pid][EGFR][-1][1] < 45
                                      or obs[pid][EGFR][-1][1] < 30) for m in meds[pid]),
    "lipid_overdue": lambda pid: not obs[pid][TC] or obs[pid][TC][-1][0] < AS_OF - timedelta(days=round(5 * 365.25)),
    "conflicting_diagnosis": lambda pid: has(pid, "E11") and all(v < 5.7 for _, v in obs[pid][HBA1C])
        and "biguanide" not in classes(pid),
    "ckd_unrecorded": lambda pid: egfr_below_60_for_90_days(pid) and not has(pid, "N18"),
    "severe_bp": lambda pid: bool(obs[pid][SBP]) and (obs[pid][SBP][-1][1] >= 180 or obs[pid][DBP][-1][1] >= 120),
}

# ---------------------------------------------------------------- 1. rules vs answer key
print("Rules vs cases.json")
for rule, fn in RULES.items():
    found = {pid for pid in patients if fn(pid)}
    expected = {c["patient_id"] for c in cases if rule in c["detected_by"]}
    check(found == expected, f"{rule:<24} found {sorted(found)}, expected {sorted(expected)}")
for c in cases:
    if c["facts"]["risk_points"] != score(c["patient_id"]):
        check(False, f"{c['id']} risk_points in cases.json disagrees with the CSVs")
check(not any(RULES[r](c["patient_id"]) for c in cases if c["type"] == "healthy_control" for r in RULES),
      "healthy control triggers no rule")

# ---------------------------------------------------------------- 2. references
print("References")
guidelines = {}
for path in sorted((CORPUS / "guidelines").glob("*.md")):
    meta, body = front_matter(path)
    guidelines[meta.get("doc_id", path.stem)] = (path, meta, body)
doc_ids = set(guidelines)
notes = {}
for path in sorted((CORPUS / "notes").glob("*.md")):
    meta, _ = front_matter(path)
    notes[path.stem] = meta
    check(meta.get("patient_id") in patients and meta.get("patient_id") == path.stem,
          f"notes/{path.name} patient_id matches a patient")
for c in cases:
    missing = set(c["expected_doc_ids"]) - doc_ids
    check(not missing, f"cases.json {c['id']} doc_ids exist" + (f" (missing {sorted(missing)})" if missing else ""))
for name in ("golden.json", "redteam.json"):
    items = json.loads((EVALS / name).read_text())
    ids = [i["id"] for i in items]
    check(len(ids) == len(set(ids)), f"evals/{name}: {len(items)} items, unique ids")
    for i in items:
        pid = i.get("patient_id")
        exists = pid is None or pid in patients or i.get("patient_must_not_exist")
        check(exists and not (i.get("patient_must_not_exist") and pid in patients),
              f"evals/{name} {i['id']} patient {pid}")
        missing = set(i.get("expected_doc_ids", [])) - doc_ids
        check(not missing, f"evals/{name} {i['id']} doc_ids exist" + (f" (missing {sorted(missing)})" if missing else ""))

# ---------------------------------------------------------------- 3. guideline corpus
print("Guidelines")
required = {"doc_id", "title", "version", "status", "updated_at", "audience"}
sizes = []
for doc_id, (path, meta, body) in guidelines.items():
    check(required <= set(meta) and BANNER in body, f"{path.name} front matter + banner")
    if meta.get("status") == "superseded":
        check(meta.get("superseded_by") in doc_ids, f"{path.name} superseded_by points to an existing doc")
    for section in re.split(r"\n(?=## )", body):
        if section.startswith("## "):
            sizes.append((len(section.split()), f"{doc_id} / {section.splitlines()[0][3:]}"))
sizes.sort()
words = sum(n for n, _ in sizes)
print(f"  {len(guidelines)} docs, {len(sizes)} sections, {words} words (~{round(words * 1.33)} tokens)")
print(f"  smallest section: {sizes[0][0]} words ({sizes[0][1]})")
print(f"  largest section:  {sizes[-1][0]} words ({sizes[-1][1]})")

# ---------------------------------------------------------------- 4. leakage
# data/ is everything the assistant may read. Eval files, answer-key fields and test explanations
# must never appear there, or the evals measure copying instead of reasoning.
print("Leakage")
LEAK_MARKERS = ["expected_doc_ids", "must_include", "must_not", "detected_by", "expected_behavior",
                "expected_patients", "test_fixture", "answer key", "golden", "red team", "redteam",
                "prompt injection", "prompt-injection", "a correct assistant"]
data_files = [p for p in (ROOT / "data").rglob("*") if p.is_file()]
odd = [str(p.relative_to(ROOT)) for p in data_files if p.suffix not in (".csv", ".md")]
check(not odd, "data/ holds only .csv and .md files" + (f" (found {odd})" if odd else ""))
case_ids = {c["id"] for c in cases}
for p in data_files:
    text = p.read_text().lower()
    hits = [m for m in LEAK_MARKERS if m in text] + sorted(i for i in case_ids if re.search(rf"\b{i}\b", p.read_text()))
    if hits:
        check(False, f"{p.relative_to(ROOT)} contains eval wording: {hits}")
check(not any((ROOT / "data").rglob("*.json")), "no JSON under data/")
print(f"  scanned {len(data_files)} files under data/ for {len(LEAK_MARKERS)} markers and {len(case_ids)} case ids")

print(f"\n{'All checks passed.' if not failures else f'{len(failures)} check(s) failed.'}")
sys.exit(1 if failures else 0)
