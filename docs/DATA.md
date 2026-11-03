# Data Guide

All data in this project is **synthetic (AI-generated)**. ShaikSure Motor Insurance is a fictional insurer.
No real customer, policy or claim data is used (privacy and DPDP Act reasons).

## Files

| File | Rows | Used for |
|---|---|---|
| `data/claims/claim_descriptions.csv` | 420 | Fine-tuning the classifier: 300 English + 120 Hinglish (50 + 20 per claim type) |
| `data/claims/hard_test_claims.csv` | 36 | Harder hand-written English test set (6 per type), never used in training |
| `data/claims/hard_test_hinglish.csv` | 12 | Harder hand-written Hinglish test set (2 per type), never used in training |
| `data/claims/customers.csv` | 60 | Policyholders (fictional names, `@example.com` emails) |
| `data/claims/vehicles.csv` | 60 | One vehicle per customer: make, model, segment, year, registration |
| `data/claims/policies.csv` | 60 | Policy type, dates, status, IDV, add-ons |
| `data/claims/past_claims.csv` | 64 | Claim history, used for the repeat-claims check |
| `data/claims/policy_rules.csv` | 6 | Limits and deductibles per claim type (SQL rules) |
| `data/claims/repair_prices.csv` | 57 | Repair cost per part, car segment and severity |
| `data/policy_docs/*.pdf` | 4 PDFs | Policy wording for RAG (Pinecone) |

## Languages

Many customers in India write in **Hinglish** (Hindi in English letters), so the data covers two forms:

| Code | Language | Example |
|---|---|---|
| `en` | English | My car was stolen from the parking |
| `hinglish` | Hindi in English letters | Meri gaadi chori ho gayi |

Customer replies follow the customer's language (English or Hinglish); adjuster messages and the audit log are always in English.

## Claim types (labels)

| Label | Meaning |
|---|---|
| `collision` | Accidental damage: hitting a vehicle, object, animal or pothole, overturning |
| `theft` | Whole vehicle or parts/accessories stolen |
| `flood` | Water damage: flooding, waterlogging, submerged vehicle, water in engine |
| `fire` | Fire, self-ignition, short circuit, lightning, explosion |
| `vandalism` | Deliberate damage by other people: scratching, stone throwing, riots, slashed tyres |
| `glass_only` | Only glass damaged by accident (stone chip, hail, falling branch), no other part |

### Labelling rules for unclear cases
1. **Label the main cause of damage.** An accident that also cracks the windshield is `collision`.
2. **Deliberate damage by people is `vandalism`**, even if only the glass broke.
3. **Burnt damage is `fire`**, even if someone set the fire on purpose.
4. **`glass_only` only when nothing except glass is damaged.**
5. **Stolen parts are `theft`**, not vandalism.

## Demo policies (fixed test scenarios)

| Policy | Customer | Scenario | Expected behaviour |
|---|---|---|---|
| SSM-2026-00001 | SK Ibrahim, Hyundai Creta 2022 | Comprehensive, Zero Dep + Engine Protect, clean history | Happy path, approve |
| SSM-2026-00002 | Swift 2021 | Comprehensive, **no Engine Protect** | Flood engine damage excluded (Section 7.5) |
| SSM-2026-00003 | - | **Third Party Only** | Own damage not covered (Section 2.3), reject |
| SSM-2026-00004 | - | **Expired** policy | Reject (Section 7.10) |
| SSM-2026-00005 | - | Policy started **10 days ago** | Human review (Section 10.2b) |
| SSM-2026-00006 | - | **3 claims** in last 12 months | Human review (Section 10.2c) |
| SSM-2026-00007 | Innova Crysta 2024 | High IDV SUV | High-value claim, human review (Section 10.2a) |

## Limits of this data
- Descriptions follow a limited set of writing patterns, so scores on `claim_descriptions.csv` will be optimistic.
  `hard_test_claims.csv` is written differently to give a more honest score.
- Only English and Hinglish are covered. Hindi script, Telugu and other Indian languages are future work.
- Real claims would include spelling mistakes, more regional languages and much longer stories.
  Before real use, the model must be tested and retrained on real, anonymised claims.
