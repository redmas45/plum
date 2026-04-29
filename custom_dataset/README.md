# Custom Dataset — 10 Manual Test Cases

> Upload these documents via the **Submit Claim** tab to validate the pipeline end-to-end with real images.

---

## How to Use

1. Run `python run.py` and open `http://127.0.0.1:8000`
2. Go to **Submit Claim**
3. Fill in the form values from the table below
4. Upload the images from the corresponding folder
5. Click **Process Claim via AI Pipeline**
6. Check the decision on the **Dashboard** → click the claim to see the full trace

---

## Test Cases

| # | Folder | Member ID | Category | Amount (₹) | Documents to Upload | Expected Decision | Why |
|---|---|---|---|---|---|---|---|
| 1 | `01_consultation_valid` | EMP001 | CONSULTATION | 1,150 | prescription.png + hospital_bill.png | **APPROVED** | Valid claim, under sub-limit (₹2,000), network hospital gets 20% discount |
| 2 | `02_pharmacy_valid` | EMP002 | PHARMACY | 613 | prescription.png + pharmacy_bill.png | **APPROVED** | Valid pharmacy claim, under sub-limit (₹15,000), correct docs |
| 3 | `03_dental_root_canal` | EMP003 | DENTAL | 5,000 | hospital_bill.png | **APPROVED** | Root canal is a covered dental procedure, under sub-limit (₹10,000) |
| 4 | `04_diagnostic_thyroid` | EMP004 | DIAGNOSTIC | 2,100 | prescription.png + lab_report.png + hospital_bill.png | **APPROVED** | Valid diagnostic claim with all 3 required docs |
| 5 | `05_vision_glasses` | EMP006 | VISION | 4,950 | prescription.png + hospital_bill.png | **APPROVED** | Under vision sub-limit (₹5,000), correct docs |
| 6 | `06_ayurveda_valid` | EMP007 | ALTERNATIVE_MEDICINE | 5,000 | prescription.png + hospital_bill.png | **REJECTED** | Amount ₹5,000 is at the per-claim limit; however total bill ₹7,300 exceeds it |
| 7 | `07_dental_excluded_whitening` | EMP009 | DENTAL | 4,500 | hospital_bill.png | **REJECTED** | Teeth whitening is an excluded dental procedure |
| 8 | `08_consultation_over_limit` | EMP001 | CONSULTATION | 7,500 | prescription.png + hospital_bill.png | **REJECTED** | ₹7,500 exceeds the per-claim limit of ₹5,000 |
| 9 | `09_consultation_wrong_docs` | EMP001 | CONSULTATION | 1,500 | prescription_only.png | **REJECTED** | Missing hospital bill — CONSULTATION requires Prescription + Hospital Bill |
| 10 | `10_diagnostic_pre_auth` | EMP008 | DIAGNOSTIC | 4,800 | prescription.png + hospital_bill.png | **REJECTED** | Missing required lab report for DIAGNOSTIC category |

---

## Detailed Scenarios

### 01 — Consultation (Valid, Should Approve)
- **Patient**: Rajesh Kumar (EMP001)
- **Scenario**: Simple URI consultation at City Medical Centre, Bengaluru
- **Documents**: Prescription (Dr. Arun Sharma) + Hospital Bill (₹1,150)
- **Expected Calculation**: ₹1,150 → capped at sub-limit ₹2,000 → OK → 10% co-pay = -₹115 → **Approved: ₹1,035**

### 02 — Pharmacy (Valid, Should Approve)
- **Patient**: Priya Singh (EMP002)
- **Scenario**: Monthly diabetes + hypertension medication from pharmacy
- **Documents**: Prescription (Dr. Priya Nair) + Pharmacy Bill (₹612.75)
- **Note**: Diagnosis is diabetes/hypertension — 90-day waiting period applies. EMP002 joined 2024-04-01, so if treatment date is recent, she's past the waiting period.

### 03 — Dental Root Canal (Valid, Should Approve)
- **Patient**: Amit Verma (EMP003)
- **Scenario**: Root canal treatment at Smile Dental Care, Pune
- **Documents**: Hospital Bill only (₹5,000) — dental only requires hospital bill
- **Note**: Root canal is explicitly in the `covered_procedures` list

### 04 — Diagnostic Thyroid (Valid, Should Approve)
- **Patient**: Sneha Reddy (EMP004)
- **Scenario**: CBC + thyroid profile tests at City Medical Centre
- **Documents**: Prescription + Lab Report + Hospital Bill (all 3 required for DIAGNOSTIC)
- **Note**: ₹2,100 is well under both per-claim (₹5,000) and diagnostic sub-limit (₹10,000)

### 05 — Vision / Glasses (Valid, Should Approve)
- **Patient**: Kavita Nair (EMP006)
- **Scenario**: Eye examination + progressive lenses at Clear Vision Eye Care, Delhi
- **Documents**: Prescription (Dr. Sunita Kapoor) + Bill (₹4,950)
- **Note**: Glasses and eye examination are covered items under vision

### 06 — Alternative Medicine / Ayurveda (Edge Case)
- **Patient**: Suresh Patil (EMP007)
- **Scenario**: Knee osteoarthritis treatment via Panchakarma at Kerala Ayurveda Centre
- **Documents**: Prescription (Vaidya Ramesh Iyer, AYUR registration) + Hospital Bill
- **Note**: Sub-limit is ₹8,000, but per-claim limit is ₹5,000. Claim amount ₹5,000 is at the boundary.

### 07 — Dental Excluded Procedure (Should Reject)
- **Patient**: Anita Desai (EMP009)
- **Scenario**: Professional teeth whitening at Sparkle Dental Studio, Hyderabad
- **Documents**: Hospital Bill (₹8,500)
- **Expected**: REJECTED — "Teeth Whitening" is explicitly in `excluded_procedures` for dental

### 08 — Consultation Over Per-Claim Limit (Should Reject)
- **Patient**: Rajesh Kumar (EMP001)
- **Scenario**: Same consultation docs but claiming ₹7,500
- **Documents**: Prescription + Hospital Bill
- **Expected**: REJECTED — ₹7,500 > ₹5,000 per-claim limit

### 09 — Wrong Documents (Should Reject Early)
- **Patient**: Rajesh Kumar (EMP001)
- **Scenario**: Submitting only a prescription for a consultation claim (no hospital bill)
- **Documents**: prescription_only.png
- **Expected**: REJECTED at Agent 1 — "CONSULTATION requires Prescription + Hospital Bill. Missing: HOSPITAL_BILL"

### 10 — Diagnostic Missing Lab Report (Should Reject)
- **Patient**: Ravi Menon (EMP008)
- **Scenario**: MRI + consultation at Apollo Chennai but no lab report uploaded
- **Documents**: Prescription + Hospital Bill (missing lab report)
- **Expected**: REJECTED at Agent 1 — "DIAGNOSTIC requires Prescription + Lab Report + Hospital Bill. Missing: LAB_REPORT"

---

## Notes

- Treatment dates should be set to **today or within the last 30 days** (the UI enforces this)
- These are AI-generated document images — the Vision LLM (Llama 4 Scout) will process them
- Results may vary slightly based on LLM interpretation of the generated images
- Check the **Pipeline Trace** on each claim to see exactly what each agent decided
