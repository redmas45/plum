# Policy Reference Guide

> All rules below are loaded at runtime from `data/policy_terms.json`. Nothing is hardcoded.

---

## Policy Overview

| Field | Value |
|---|---|
| **Policy ID** | PLUM_GHI_2024 |
| **Policy Name** | Group Health Insurance — Standard Plan |
| **Insurer** | ICICI Lombard General Insurance |
| **Company** | TechCorp Solutions Pvt Ltd (500 employees) |
| **Policy Period** | 2024-04-01 to 2025-03-31 |
| **Status** | ACTIVE |

---

## Coverage Limits

| Limit Type | Amount |
|---|---|
| Sum Insured (per employee) | ₹5,00,000 |
| Annual OPD Limit | ₹50,000 |
| **Per-Claim Limit** | **₹5,000** |
| Family Floater Combined | ₹1,50,000 |

---

## Category-Wise Sub-Limits & Rules

| Category | Sub-Limit | Co-Pay | Network Discount | Prescription Required? |
|---|---|---|---|---|
| **CONSULTATION** | ₹2,000 | 10% | 20% | Yes |
| **DIAGNOSTIC** | ₹10,000 | 0% | 10% | Yes |
| **PHARMACY** | ₹15,000 | 0% (30% for branded drugs) | — | Yes |
| **DENTAL** | ₹10,000 | 0% | — | No |
| **VISION** | ₹5,000 | 0% | — | Yes |
| **ALTERNATIVE_MEDICINE** | ₹8,000 | 0% | — | Yes |

> **Note**: The global per-claim limit of ₹5,000 applies *before* category sub-limits. A ₹7,500 diagnostic claim is rejected at the global level, even though diagnostic sub-limit is ₹10,000.

---

## Required Documents Per Category

| Category | Required | Optional |
|---|---|---|
| **CONSULTATION** | Prescription + Hospital Bill | Lab Report, Diagnostic Report |
| **DIAGNOSTIC** | Prescription + Lab Report + Hospital Bill | Discharge Summary |
| **PHARMACY** | Prescription + Pharmacy Bill | — |
| **DENTAL** | Hospital Bill | Prescription, Dental Report |
| **VISION** | Prescription + Hospital Bill | — |
| **ALTERNATIVE_MEDICINE** | Prescription + Hospital Bill | — |

---

## Waiting Periods

| Condition | Waiting Period |
|---|---|
| **Initial (all claims)** | 30 days from join date |
| Pre-existing conditions | 365 days |
| Diabetes | 90 days |
| Hypertension | 90 days |
| Thyroid disorders | 90 days |
| Joint replacement | 730 days (2 years) |
| Maternity | 270 days (9 months) |
| Mental health | 180 days |
| Obesity treatment | 365 days |
| Hernia | 365 days |
| Cataract | 365 days |

---

## Exclusions

### General Exclusions (All Categories)
- Self-inflicted injuries
- War or nuclear hazard
- Substance abuse treatment
- Experimental treatments
- Infertility and assisted reproduction
- Obesity and weight loss programs
- Bariatric surgery
- Cosmetic or aesthetic procedures
- Vaccination (non-medically necessary)
- Health supplements and tonics

### Dental-Specific Exclusions
- Teeth whitening
- Orthodontic treatment
- Cosmetic dental procedures

### Vision-Specific Exclusions
- LASIK
- Refractive surgery

### Dental Covered Procedures
- Root Canal Treatment, Tooth Extraction, Dental Filling
- Scaling and Polishing, Dental X-Ray, Crown Placement, Gum Treatment

### Dental Excluded Procedures
- Teeth Whitening, Veneers, Orthodontic Treatment (Braces)
- Implants (Cosmetic), Bleaching

### Vision Covered Items
- Glasses, Contact Lenses, Eye Examination, Cataract Surgery

### Vision Excluded Items
- LASIK Surgery, Cosmetic Eye Surgery, Refractive Surgery

---

## Pre-Authorization Requirements

Pre-authorization is required for:
- MRI scan (amount > ₹10,000)
- CT scan (amount > ₹10,000)
- PET scan
- Major surgical procedures
- Planned hospitalization

**Validity**: 30 days from authorization.

---

## Network Hospitals

Claims from network hospitals receive additional discounts as specified per category.

| # | Hospital |
|---|---|
| 1 | Apollo Hospitals |
| 2 | Fortis Healthcare |
| 3 | Max Healthcare |
| 4 | Manipal Hospitals |
| 5 | Narayana Health |
| 6 | Medanta |
| 7 | Kokilaben Dhirubhai Ambani Hospital |
| 8 | Aster CMI Hospital |
| 9 | Columbia Asia |
| 10 | Sakra World Hospital |

---

## Submission Rules

| Rule | Value |
|---|---|
| Deadline (from treatment date) | 30 days |
| Minimum claim amount | ₹500 |
| Currency | INR |

---

## Fraud Detection Thresholds

| Threshold | Value |
|---|---|
| Same-day claims limit | 2 |
| Monthly claims limit | 6 |
| High-value claim threshold | ₹25,000 |
| Auto manual review above | ₹25,000 |
| Fraud score → manual review | ≥ 0.80 |

---

## Member Roster (12 Members)

| Member ID | Name | DOB | Gender | Relationship | Join Date |
|---|---|---|---|---|---|
| EMP001 | Rajesh Kumar | 1985-03-15 | M | SELF | 2024-04-01 |
| EMP002 | Priya Singh | 1990-07-22 | F | SELF | 2024-04-01 |
| EMP003 | Amit Verma | 1988-11-05 | M | SELF | 2024-04-01 |
| EMP004 | Sneha Reddy | 1992-02-28 | F | SELF | 2024-04-01 |
| EMP005 | Vikram Joshi | 1979-09-10 | M | SELF | **2024-09-01** |
| EMP006 | Kavita Nair | 1983-06-18 | F | SELF | 2024-04-01 |
| EMP007 | Suresh Patil | 1975-12-30 | M | SELF | 2024-04-01 |
| EMP008 | Ravi Menon | 1987-04-14 | M | SELF | 2024-04-01 |
| EMP009 | Anita Desai | 1993-08-25 | F | SELF | 2024-04-01 |
| EMP010 | Deepak Shah | 1980-01-07 | M | SELF | 2024-04-01 |
| DEP001 | Sunita Kumar | 1987-05-20 | F | SPOUSE (of EMP001) | — |
| DEP002 | Arjun Kumar | 2015-08-12 | M | CHILD (of EMP001) | — |

> **Note**: EMP005 (Vikram Joshi) joined on **2024-09-01** — 5 months later than everyone else. This is specifically used to test the 30-day initial waiting period (TC005).

---

## Financial Calculation Formula

```
1. Start with claimed_amount
2. Check: claimed_amount ≤ per_claim_limit (₹5,000)?  → If no, REJECT
3. Evaluate line items → remove excluded procedures → get approved_base
4. Cap at category sub-limit
5. Apply network discount (if network hospital):  amount = base - (base × discount%)
6. Apply co-pay:  final = amount - (amount × copay%)
7. Final approved amount = result of step 6
```

---

*All data sourced from `data/policy_terms.json` — the single source of truth for all policy rules.*
