---
doc_id: ops-01
title: Referral and escalation routes
version: 5.0
status: current
updated_at: 2026-03-16
audience: internal
---
# Referral and escalation routes

> **Mock document for a software demo. Not clinical guidance; do not use for patient care.**
> Example Clinic internal policy. All extensions and inboxes are fictional.

## Response times

| Route | When | Response time | How |
|---|---|---|---|
| Emergency department | hypertensive emergency (htn-03), any acute chest pain or stroke signs | immediately | call an ambulance; then call the duty clinician on ext. 4400 |
| Same-day clinician review | hypertensive urgency (htn-03); a new result that needs a dose change today | same day | duty clinician, ext. 4400 |
| Pharmacist medication review | a dose that exceeds the kidney limit (ckd-02); interacting medicines | within 2 weeks | clinic pharmacist inbox "meds-review" |
| Diabetes educator | new diabetes diagnosis (dm-01); prediabetes lifestyle program (dm-02) | within 4 weeks | "diabetes-education" inbox |
| Hypertension clinic | confirmed resistant hypertension (htn-02) | within 6 weeks | referral form HTN-R |
| Nephrology | criteria in ckd-01 | within 6 weeks; within 2 weeks if eGFR below 30 | referral form NEPH-R |

## Who acts on a flag

The patient's primary clinician owns every flag about that patient. A flag raised by software, including an AI assistant, is a suggestion for the clinician to review. It is never an order and never sent to the patient directly.

When the primary clinician is away, flags in the "same day" or "immediately" rows go to the duty clinician. All other flags wait in the primary clinician's queue.

## What a good flag contains

1. The patient id and the finding in one sentence.
2. The numbers and dates it rests on.
3. The protocol that applies, by doc_id.
4. The route from the table above.
5. Anything uncertain, such as missing data or conflicting records.
