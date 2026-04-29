# Plum AI Claims Processing System

A multi-agent, AI-powered health insurance claims processing system. This project automates the assessment of medical claims by orchestrating a pipeline of specialized LLM agents (powered by Groq and Llama models) to perform document verification, policy checking, fraud detection, and final claim adjudication.

## 🌟 Key Features

- **Multi-Agent Pipeline**: Utilizes an orchestrated flow of 5 specialized AI agents (Doc Verifier, Doc Parser, Policy Checker, Fraud Detector, Decision Maker).
- **Explainable AI (XAI)**: Generates a complete "Pipeline Trace" for every claim, breaking down agent reasoning, confidence scores, and token usage step-by-step.
- **Vision Models Integration**: Uses Llama 4 Scout (Vision) to extract data directly from handwritten hospital receipts and uploaded documents.
- **Dynamic Frontend Dashboard**: A modern, responsive Single Page Application (SPA) to submit claims, review decisions, and download beautiful, print-ready PDF summaries.
- **Evaluation Suite**: Built-in test suite to evaluate the model's accuracy against historical medical claims, featuring detailed metrics and performance tracking.

## 🏗️ Technology Stack

- **Backend**: Python, FastAPI, Pydantic
- **AI / LLMs**: Groq API (Llama 3.3 70B Versatile, Llama 4 Scout 17B Instruct)
- **Database**: SQLite (via aiosqlite for async support)
- **Frontend**: Vanilla HTML, CSS, JavaScript (No complex build steps required)

## 🚀 Local Development Setup

### Prerequisites
- Python 3.11+
- A Groq API Key (`GROQ_API_KEY`)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/redmas45/plum.git
   cd plum
   ```

2. **Create a virtual environment (Optional but recommended)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**
   - Copy the `.env.example` file and rename it to `.env`.
   - Open `.env` and add your Groq API Key:
   ```env
   GROQ_API_KEY=your_actual_groq_api_key_here
   ```

   The `.env` file also exposes **confidence scoring tunables** — no code changes needed to adjust system strictness:

   | Variable | Default | What It Controls |
   |---|---|---|
   | `INITIAL_CONFIDENCE` | 1.0 | Starting confidence for every claim |
   | `CONFIDENCE_DEDUCT_UNREADABLE_DOC` | 0.5 | Blurry/unreadable document penalty |
   | `CONFIDENCE_DEDUCT_MISSING_DOC` | 1.0 | Wrong document type (instant reject) |
   | `CONFIDENCE_DEDUCT_PATIENT_MISMATCH` | 1.0 | Name mismatch across docs (instant reject) |
   | `CONFIDENCE_DEDUCT_POOR_QUALITY` | 0.05 | Low quality but readable doc |
   | `CONFIDENCE_DEDUCT_COMPONENT_FAILURE` | 0.2 | Agent crash / graceful degradation |
   | `CONFIDENCE_DEDUCT_POLICY_VIOLATION` | 1.0 | Policy rule violation (instant reject) |
   | `CONFIDENCE_DEDUCT_LLM_FALLBACK` | 0.05 | LLM unavailable, rules-only fallback |
   | `CONFIDENCE_DEDUCT_FRAUD_SAME_DAY` | 0.15 | Same-day claims exceeded |
   | `CONFIDENCE_DEDUCT_DOC_INCONSISTENCY` | 0.1 | Inconsistent data across documents |

5. **Run the Server**
   ```bash
   python run.py
   ```
   - The API and Dashboard will be available at: `http://127.0.0.1:8000`

---

## ☁️ Deployment (Railway)

This application is configured for seamless deployment on [Railway.app](https://railway.app/).

### Step-by-Step Railway Deployment:

1. **Create a Railway Account**: Sign up or log in to [Railway](https://railway.app/).
2. **New Project**: Click **New Project** -> **Deploy from GitHub repo**.
3. **Select Repository**: Choose your `plum` repository.
4. **Environment Variables**:
   - Before the deployment finishes, go to the **Variables** tab in your Railway dashboard.
   - Add the following variables:
     - `GROQ_API_KEY`: (Paste your Groq API Key here)
     - `APP_ENV`: `production`
5. **Add a Volume for SQLite persistence** (Crucial):
   - In the Railway dashboard, go to the **Settings** tab.
   - Scroll down to **Volumes** and click **New Volume**.
   - Mount the volume to the absolute path `/app/data`.
   - Update your environment variable to point to the mounted volume:
     - `DATABASE_URL`: `sqlite+aiosqlite:////app/data/claims.db`
6. **Generate Domain**:
   - Go to the **Settings** tab -> **Networking**.
   - Click **Generate Domain** to get a public, shareable HTTPS URL.
7. **Deploy**:
   - Railway will use the provided `Dockerfile` or `railway.toml` to automatically build and launch the FastAPI server.

## 📋 Policy Rules Quick Reference

> All rules are loaded at runtime from `data/policy_terms.json`. Nothing is hardcoded. For the complete reference, see [`docs/policy_reference.md`](docs/policy_reference.md).

### Coverage Limits

| Limit Type | Amount |
|---|---|
| Sum Insured (per employee) | ₹5,00,000 |
| Annual OPD Limit | ₹50,000 |
| **Per-Claim Limit** | **₹5,000** |
| Family Floater Combined | ₹1,50,000 |

### Category Sub-Limits & Financial Rules

| Category | Sub-Limit | Co-Pay | Network Discount |
|---|---|---|---|
| CONSULTATION | ₹2,000 | 10% | 20% |
| DIAGNOSTIC | ₹10,000 | 0% | 10% |
| PHARMACY | ₹15,000 | 0% (30% branded) | — |
| DENTAL | ₹10,000 | 0% | — |
| VISION | ₹5,000 | 0% | — |
| ALTERNATIVE_MEDICINE | ₹8,000 | 0% | — |

### Required Documents Per Category

| Category | Required Documents | Optional |
|---|---|---|
| CONSULTATION | Prescription + Hospital Bill | Lab Report, Diagnostic Report |
| DIAGNOSTIC | Prescription + Lab Report + Hospital Bill | Discharge Summary |
| PHARMACY | Prescription + Pharmacy Bill | — |
| DENTAL | Hospital Bill only | Prescription, Dental Report |
| VISION | Prescription + Hospital Bill | — |
| ALTERNATIVE_MEDICINE | Prescription + Hospital Bill | — |

### Key Conditions

- **Waiting Period**: 30-day initial waiting period from member's join date. Condition-specific waiting periods range from 90 days (diabetes, hypertension) to 730 days (joint replacement).
- **Exclusions**: Cosmetic procedures, self-inflicted injuries, substance abuse, experimental treatments, teeth whitening, LASIK, etc.
- **Pre-Authorization**: Required for MRI/CT/PET scans above ₹10,000 and major surgical procedures.
- **Submission Deadline**: Claims must be submitted within 30 days of treatment date.
- **Minimum Claim**: ₹500.

### Fraud Thresholds

| Rule | Limit |
|---|---|
| Same-day claims | Max 2 per day |
| Monthly claims | Max 6 per month |
| High-value auto-review | ≥ ₹25,000 |

### Network Hospitals (10)
Apollo, Fortis, Max, Manipal, Narayana Health, Medanta, Kokilaben, Aster CMI, Columbia Asia, Sakra World.

---

## 🧪 Internal Testing & Model Evaluation

Unlike traditional ML models that use metrics like **R²** (for regression) or **mAP50-95** (for object detection), evaluating an LLM classification and reasoning pipeline requires distinct metrics. 

To run the automated evaluation suite:
1. Ensure your local server is running (`python run.py`).
2. Open a new terminal and run the report generator:
   ```bash
   python generate_eval_report.py
   ```

The system will evaluate the 12 edge-case test claims defined in `data/test_cases.json` and print advanced LLM classification metrics directly to your terminal:

```text
==================================================
🚀 MODEL EVALUATION & PERFORMANCE SUMMARY
==================================================
Total Cases Run : 12
Passed          : 11
Failed          : 1
Errors          : 0
--------------------------------------------------
📊 CLASSIFICATION METRICS (Like mAP95 / R^2)
Overall Accuracy: 91.7%
Mean Confidence : 88.5%
Fault Tolerance : 2/12 cases gracefully degraded
--------------------------------------------------
🤖 LLM EFFICIENCY STATS
Vision Model    : meta-llama/llama-4-scout-17b-16e-instruct
Text Model      : meta-llama/llama-3.3-70b-versatile
Total API Calls : 44
Token Efficiency: 1250 tokens / case
Total Eval Time : 31.10 seconds
Avg Latency     : 2.59 seconds / case
==================================================
```

This ensures we can actively monitor token cost, processing latency, and pipeline reasoning accuracy with every iteration.

> **Formal Eval Report**: Available as a downloadable deliverable via the **Run Eval** tab in the dashboard, or directly at `/eval/report/download`. Full per-test-case analysis with traces and failure analysis: [`docs/eval_report.md`](docs/eval_report.md).

## 🧬 Unit Tests

The system has **92 unit tests** covering all significant components. Tests run without any LLM API calls (mocked).

```bash
python -m pytest tests/ -v
```

| Test File | Tests | What It Covers |
|---|---|---|
| `test_confidence.py` | 17 | Confidence scoring: deductions, caps, boosts, floors |
| `test_policy.py` | 25 | Policy terms: members, coverage, doc requirements, thresholds |
| `test_doc_verifier.py` | 14 | Doc verification: type checking, name matching, quality |
| `test_policy_checker.py` | 10 | Policy rules: limits, waiting periods, exclusions, financial math |
| `test_fraud_detector.py` | 10 | Fraud detection: same-day limits, high-value flags, consistency |

```text
========================= 92 passed in 0.79s =========================
```

## 🗂️ Custom Test Dataset

The `custom_dataset/` folder contains **10 manually curated test cases** with AI-generated Indian medical document images (prescriptions, hospital bills, lab reports, pharmacy bills) for end-to-end validation via the UI.

Covers all 6 claim categories + edge cases: wrong documents, excluded procedures, over-limit claims.

See [`custom_dataset/README.md`](custom_dataset/README.md) for the complete guide with form values and expected results.

## 📊 Pipeline Overview

1. **User submits claim** via the frontend (Member ID, Category, Amount, Documents).
2. **Doc Verifier**: Validates document authenticity and legibility.
3. **Doc Parser**: Extracts structured data (line items, costs) from receipts using Vision LLM.
4. **Policy Checker**: Cross-references the extracted data against the member's policy terms (Coverage limits, exclusions).
5. **Fraud Detector**: Analyzes claim patterns and descriptions for anomalies or synthetic fraud.
6. **Decision Maker**: Synthesizes reports from all previous agents and generates a final adjudication decision (APPROVED, REJECTED, MANUAL_REVIEW) with an approved amount and a human-readable summary.

## 📖 Documentation

| Document | Description |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System design, component contracts, data flow |
| [`docs/policy_reference.md`](docs/policy_reference.md) | Complete policy rules reference (from `policy_terms.json`) |
| [`docs/eval_report.md`](docs/eval_report.md) | Formal evaluation report — Deliverable #4 |
| [`custom_dataset/README.md`](custom_dataset/README.md) | 10 custom test cases guide |

---
*Built by Rajiv Kumar for Plum AI*
