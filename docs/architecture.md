# Multi-Agent Health Insurance Claims Processing System

## Overview

This project implements an intelligent, automated pipeline for processing health insurance claims. It uses a multi-agentic architecture powered by LLMs (Llama 4 Scout for vision, Llama 3.3 70B for text reasoning) to verify documents, extract structured data, apply complex policy rules, detect fraud, and make explainable claim decisions.

## Multi-Agent Architecture

The system is designed as a sequential pipeline of 5 specialized agents, coordinated by a central Orchestrator. This separation of concerns ensures explainability, fault tolerance, and clear component boundaries.

### 1. Document Verifier (Agent 1)
- **Role:** The gatekeeper. Ensures the member uploaded the correct and readable documents before any costly processing happens.
- **Model:** Llama 4 Scout (Vision)
- **Design Decision:** Early rejection saves computation. By analyzing document metadata and image quality first, we can give immediate, actionable feedback to the user (e.g., "You uploaded a lab report, but a prescription is required").

### 2. Document Parser (Agent 2)
- **Role:** The extractor. Converts unstructured images (prescriptions, bills, lab reports) into structured JSON.
- **Model:** Llama 4 Scout (Vision)
- **Design Decision:** Uses specific prompt templates per document type to improve extraction accuracy. Captures confidence scores and quality warnings for downstream use.

### 3. Policy Checker (Agent 3)
- **Role:** The rules engine. Evaluates the extracted claim data against the `policy_terms.json`.
- **Model:** Python Deterministic Logic + Llama 3.3 70B
- **Design Decision:** **Hybrid Approach.** Hard math (per-claim limits, sub-limits, co-pay calculations) and deterministic checks (waiting periods) are handled by Python code for 100% accuracy. Complex reasoning (e.g., matching a diagnosis to a generic policy exclusion) is delegated to the LLM.

### 4. Fraud Detector (Agent 4)
- **Role:** The risk analyst. Looks for suspicious patterns in the current claim and historical claims.
- **Model:** Python Logic + Llama 3.3 70B
- **Design Decision:** It does not reject claims; it only flags them (`MANUAL_REVIEW`) and produces a fraud score. It checks same-day claim limits, high-value thresholds, and document inconsistencies.

### 5. Decision Maker (Agent 5)
- **Role:** The synthesizer. Takes the outputs of all previous agents and formulates the final `APPROVED`, `PARTIAL`, `REJECTED`, or `MANUAL_REVIEW` decision.
- **Model:** Llama 3.3 70B
- **Design Decision:** Ensures explainability. It aggregates the reasons, line-item decisions, and confidence scores into a single cohesive response.

## Traceability & Observability

A core requirement was that every decision must be explainable. This is achieved via the `ClaimTrace`.
- Every agent execution is wrapped in an `AgentStep`.
- The `AgentStep` records input summaries, outputs, LLM tokens used, processing time, and any deductions to the `ConfidenceTracker`.
- The final payload includes the full trace, allowing human operators to see exactly which agent made which decision.

## Design Alternatives Considered and Rejected

During the design phase, several alternative architectures were evaluated and ultimately rejected:

1. **Single Monolithic LLM Call:**
   - *Considered:* Passing all raw text and document OCR into a single massive LLM prompt and asking for a final "APPROVED/REJECTED" output.
   - *Rejected:* This black-box approach violates the Explainable AI (XAI) requirement. If the model rejects a claim, it is impossible to debug whether it misread the receipt or misunderstood the policy. It also costs significantly more tokens for simple rejections.
2. **Pure Deterministic Rules Engine (No LLM):**
   - *Considered:* Building massive if/else trees for all policy terms and using traditional OCR (like Tesseract).
   - *Rejected:* Traditional OCR struggles heavily with handwritten medical receipts. Furthermore, writing hardcoded rules for every possible medical diagnosis mapping is impossible at scale. The LLM provides necessary semantic reasoning.
3. **Fully Asynchronous Event-Driven Architecture (Kafka/RabbitMQ):**
   - *Considered:* Decoupling every agent into its own microservice communicating via message queues.
   - *Rejected:* Over-engineering for the current scope. It introduces massive infrastructure complexity (managing queues, distributed tracing, eventual consistency). The sequential Orchestrator pattern provides the necessary separation of concerns without the deployment nightmare, and can be easily migrated to Celery/Temporal later if 10x scale is reached.

## Graceful Degradation

If an agent fails (e.g., LLM timeout, parsing error), the pipeline does not crash (Test Case TC011).
- The `Orchestrator` catches exceptions.
- The `FailureRecord` is logged in the `ClaimTrace`.
- The `ConfidenceTracker` applies a heavy deduction.
- The pipeline continues with partial data, or the `DecisionMaker` forces a `MANUAL_REVIEW` due to low confidence.

## Limitations and Scaling to 10x Load

### Current Limitations:
1. **Synchronous LLM Calls:** Processing is currently sequential for a single claim. Vision model calls can take 5-10 seconds.
2. **SQLite Database:** Uses `aiosqlite` which is fine for this assignment but will become a bottleneck.
3. **In-Memory File Handling:** Uploads are saved to local disk.

### Addressing 10x Load:
1. **Asynchronous Task Queues:** Move claim processing to background workers (e.g., Celery or Temporal) instead of blocking the HTTP request. Return a `processing` status and use WebSockets/Polling for completion.
2. **Parallel Agent Execution:** While Agent 1 and 2 must be somewhat sequential, Agent 3 (Policy) and Agent 4 (Fraud) could potentially run in parallel once data is extracted.
3. **Database Migration:** Move from SQLite to PostgreSQL.
4. **Cloud Storage:** Store document images in S3 instead of local disk.
5. **Caching:** Cache LLM responses for identical document hashes or policy queries.
6. **Model Distillation:** Fine-tune smaller models for specific tasks (e.g., document classification) instead of using the large general models for everything.
