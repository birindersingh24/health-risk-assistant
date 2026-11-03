---
doc_id: risk-01
title: Example Clinic Cardiovascular Risk Points (teaching score)
version: 1.0
status: current
updated_at: 2025-06-30
audience: clinician
---
# Example Clinic Cardiovascular Risk Points (teaching score)

> **Mock document for a software demo. Not clinical guidance; do not use for patient care.**
> This is a simplified points score made up for teaching. It is not a validated risk equation and its bands are not percentages.

## Purpose and limits

The score sorts adults without known heart disease or stroke into four bands that drive the statin advice in lip-01 and the treatment thresholds in htn-02. It is a teaching stand-in for validated 10-year risk calculators.

Do not use it for patients who already have cardiovascular disease (previous heart attack, stroke, or peripheral arterial disease). They need a statin regardless of the score. Do not quote the score as a percentage chance of a heart attack.

## Points

| Factor | Points |
|---|---|
| Age below 40 / 40 to 49 / 50 to 59 / 60 to 69 / 70 or older | 0 / 2 / 4 / 6 / 8 |
| Male sex | 1 |
| Current smoker (former smokers score 0) | 3 |
| Diabetes on the active problem list | 3 |
| Latest systolic BP below 120 / 120 to 139 / 140 to 159 / 160 or higher | 0 / 1 / 2 / 3 |
| Currently taking any blood pressure medicine | 1 |
| Total cholesterol to HDL ratio below 4 / 4 to 5.9 / 6 or higher | 0 / 1 / 2 |
| Premature heart disease in a parent or sibling (a man before 55, a woman before 65) | 1 |

Age is age on the day of calculation. Use the most recent systolic reading and the most recent lipid panel. Compute the ratio from that panel and do not round it before comparing it with the table: 3.96 scores 0.

## Bands

| Total points | Band |
|---|---|
| 0 to 5 | low |
| 6 to 8 | borderline |
| 9 to 11 | intermediate |
| 12 or more | high |

## Inputs that live outside the structured record

Family history and smoking status are often recorded only in visit notes, or updated there before the structured fields. Before reporting a band, check the notes for a family history of premature heart disease and for changes in smoking. If a note adds a factor the structured data lacks, recalculate and say which source changed the result.

If the latest lipid panel is more than five years old, the score is unreliable (lip-01): report it with that warning.
