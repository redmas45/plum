# Plum AI Claims Processing System

An intelligent, multi-agent pipeline for processing health insurance claims, built for the Plum AI Engineer assignment.

## System Overview

This system automates the processing of health insurance claims using a 5-agent architecture:
1. **Document Verifier:** Validates document types, readability, and patient name consistency using Vision LLMs.
2. **Document Parser:** Extracts structured data (line items, diagnoses, amounts) from raw images.
3. **Policy Checker:** Evaluates extracted data against complex policy rules (waiting periods, exclusions, limits, co-pays).
4. **Fraud Detector:** Analyzes claim history and document consistency to flag suspicious patterns.
5. **Decision Maker:** Synthesizes all inputs into an explainable final decision (`APPROVED`, `PARTIAL`, `REJECTED`, or `MANUAL_REVIEW`).

## Features

- **Multi-Agent Pipeline:** 5 distinct agents coordinated by an Orchestrator.
- **Explainable AI:** Every decision includes a full `ClaimTrace` detailing exactly what each agent did, how long it took, and how it affected the confidence score.
- **Graceful Degradation:** If an agent fails (simulated in TC011), the pipeline catches it, logs a `FailureRecord`, deducts confidence, and continues processing safely.
- **Premium UI:** A modern, single-page application dashboard for submitting claims, reviewing decisions, and running the evaluation suite.
- **Comprehensive Evaluation:** Built-in test runner for all 12 assignment test cases.

## Tech Stack

- **Backend:** Python 3.11, FastAPI, aiosqlite, Pydantic
- **AI Integration:** Groq API (Llama 4 Scout Vision, Llama 3.3 70B Text)
- **Frontend:** Vanilla JS, HTML, CSS (No build steps required)

## Local Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd plum-claims
   ```

2. **Set up Python environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and add your **Groq API Key**:
   ```
   GROQ_API_KEY=gsk_your_key_here
   ```

4. **Run the Application:**
   Use the provided runner script:
   ```bash
   python run.py
   ```
   *The API and UI will be available at http://127.0.0.1:8000*

## Using the UI

The application includes a built-in dashboard accessible at the root URL:
- **Dashboard:** View all processed claims.
- **Submit Claim:** Upload files and submit a new claim through the AI pipeline.
- **Run Eval:** Execute all 12 test cases automatically and view the results.

## Documentation

- [Architecture Design](docs/architecture.md)
- [Component Contracts](docs/component_contracts.md)

## Evaluation Report

You can run the full evaluation suite from the UI by navigating to the "Run Eval" tab. This will process all test cases from `data/test_cases.json` and compare the system's output against the expected results.
