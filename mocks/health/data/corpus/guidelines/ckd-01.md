---
doc_id: ckd-01
title: Chronic kidney disease detection and staging
version: 2.2
status: current
updated_at: 2025-04-14
audience: clinician
---
# Chronic kidney disease: detection and staging

> **Mock document for a software demo. Not clinical guidance; do not use for patient care.**
> Example Clinic Protocols, Primary Care.

## Who to test

Check eGFR and urine albumin-to-creatinine ratio (ACR) once a year in patients with diabetes or hypertension, and in anyone with a family history of kidney failure.

## Definition

Chronic kidney disease (CKD) means an eGFR below 60, or an ACR of 30 mg/g or higher, that has lasted for more than three months. A single low result is not enough. Repeat it within three months. If two results at least 90 days apart both meet the definition, the patient has CKD.

## Staging

Stage by the latest eGFR (G) and the latest ACR (A), and write both, for example "CKD G3a A2".

| eGFR category | eGFR (mL/min/1.73m2) |
|---|---|
| G1 | 90 or higher (CKD only if ACR is raised) |
| G2 | 60 to 89 (CKD only if ACR is raised) |
| G3a | 45 to 59 |
| G3b | 30 to 44 |
| G4 | 15 to 29 |
| G5 | below 15 |

| ACR category | ACR (mg/g) |
|---|---|
| A1 | below 30 |
| A2 | 30 to 300 |
| A3 | above 300 |

Code CKD on the problem list with the N18 code for its stage (for example N18.31 for stage 3a) and update the code when the stage changes. A coded stage that no longer matches the latest eGFR should be updated by the clinician.

## Follow-up and referral

| Stage | Recheck eGFR and ACR |
|---|---|
| G1 to G2 with raised ACR | once a year |
| G3a or G3b | every 6 months |
| G4 | every 3 months |

Refer to nephrology (ops-01) when eGFR is below 30, ACR is above 300, or kidney function is falling fast: a sustained fall of more than 5 per year, or a move to a worse G category together with a 25% drop from baseline.

Review every medicine whose dose depends on kidney function each time eGFR is reported. For metformin, follow ckd-02.
