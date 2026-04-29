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

## 📊 Pipeline Overview

1. **User submits claim** via the frontend (Member ID, Category, Amount, Documents).
2. **Doc Verifier**: Validates document authenticity and legibility.
3. **Doc Parser**: Extracts structured data (line items, costs) from receipts using Vision LLM.
4. **Policy Checker**: Cross-references the extracted data against the member's policy terms (Coverage limits, exclusions).
5. **Fraud Detector**: Analyzes claim patterns and descriptions for anomalies or synthetic fraud.
6. **Decision Maker**: Synthesizes reports from all previous agents and generates a final adjudication decision (APPROVED, REJECTED, MANUAL_REVIEW) with an approved amount and a human-readable summary.

---
*Built by Rajiv Kumar for Plum AI*
