"""
Eval routes — run all test cases from test_cases.json.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.agents.orchestrator import Orchestrator
from app.api.dependencies import get_llm_client, get_policy
from app.config import settings
from app.models.claim import ClaimCategory, ClaimRecord, DocumentMeta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eval", tags=["Evaluation"])


@router.get("/report/download")
async def download_eval_report():
    """Download the formal evaluation report (Deliverable #4)."""
    report_path = Path("docs/eval_report.md")
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Eval report not found. Generate it first.")
    return FileResponse(
        path=str(report_path),
        filename="Plum_AI_Eval_Report.md",
        media_type="text/markdown",
    )


@router.post("/run-all")
async def run_all_test_cases():
    """Run all 12 test cases and return results."""
    start_time = time.time()
    try:
        # Load test cases
        test_file = Path(settings.test_cases_file)
        if not test_file.exists():
            raise HTTPException(status_code=404, detail="test_cases.json not found")

        with open(test_file, "r", encoding="utf-8") as f:
            test_data = json.load(f)

        test_cases = test_data.get("test_cases", [])
        if not test_cases:
            raise HTTPException(status_code=404, detail="No test cases found")

        policy = get_policy()
        llm = get_llm_client()
        orchestrator = Orchestrator(llm, policy)

        results = []

        for tc in test_cases:
            case_id = tc["case_id"]
            logger.info(f"Running test case: {case_id} — {tc['case_name']}")

            try:
                inp = tc["input"]

                # Build document metas
                doc_metas = []
                for d in inp.get("documents", []):
                    doc_metas.append(DocumentMeta(
                        file_id=d.get("file_id", ""),
                        file_name=d.get("file_name", "test_doc.jpg"),
                        actual_type=d.get("actual_type"),
                        content=d.get("content"),
                        quality=d.get("quality", "GOOD"),
                        patient_name_on_doc=d.get("patient_name_on_doc"),
                    ))

                record = ClaimRecord(
                    member_id=inp["member_id"],
                    policy_id=inp.get("policy_id", "PLUM_GHI_2024"),
                    claim_category=ClaimCategory(inp["claim_category"]),
                    treatment_date=inp["treatment_date"],
                    claimed_amount=inp["claimed_amount"],
                    hospital_name=inp.get("hospital_name"),
                    documents=doc_metas,
                    ytd_claims_amount=inp.get("ytd_claims_amount", 0),
                    claims_history=inp.get("claims_history"),
                    simulate_component_failure=inp.get("simulate_component_failure", False),
                )

                decision, trace = await orchestrator.process_claim(record)

                # Compare with expected
                expected = tc.get("expected", {})
                expected_decision = expected.get("decision")
                actual_decision = decision.decision.value

                match = None
                if expected_decision:
                    match = actual_decision == expected_decision

                results.append({
                    "case_id": case_id,
                    "case_name": tc["case_name"],
                    "description": tc["description"],
                    "input_amount": inp.get("claimed_amount", "N/A"),
                    "input_category": inp.get("claim_category", "N/A"),
                    "expected_decision": expected_decision,
                    "actual_decision": actual_decision,
                    "match": match,
                    "expected": expected,
                    "decision": decision.model_dump(),
                    "trace_summary": {
                        "steps": len(trace.steps),
                        "failures": len(trace.failures),
                        "confidence": trace.overall_confidence,
                        "degraded": trace.pipeline_degraded,
                        "duration_ms": trace.total_duration_ms,
                    },
                    "status": "PASS" if match or match is None else "FAIL",
                })

            except Exception as e:
                logger.error(f"Test case {case_id} failed: {e}", exc_info=True)
                results.append({
                    "case_id": case_id,
                    "case_name": tc["case_name"],
                    "status": "ERROR",
                    "error": str(e),
                })

        # Summary
        passed = sum(1 for r in results if r.get("status") == "PASS")
        failed = sum(1 for r in results if r.get("status") == "FAIL")
        errors = sum(1 for r in results if r.get("status") == "ERROR")

        end_time = time.time()
        total_time_sec = end_time - start_time
        
        # Calculate Advanced Metrics
        total = len(results)
        accuracy = (passed / total * 100) if total > 0 else 0.0
        
        avg_confidence = sum(r.get("trace_summary", {}).get("confidence", 0) for r in results) / total if total > 0 else 0.0
        degraded_cases = sum(1 for r in results if r.get("trace_summary", {}).get("degraded", False))
        
        avg_tokens = llm.stats['total_tokens'] / total if total > 0 else 0
        avg_time = total_time_sec / total if total > 0 else 0
        
        # Print Eval Stats to Terminal
        print("\n" + "="*50)
        print("MODEL EVALUATION & PERFORMANCE SUMMARY")
        print("="*50)
        print(f"Total Cases Run : {total}")
        print(f"Passed          : {passed}")
        print(f"Failed          : {failed}")
        print(f"Errors          : {errors}")
        print("-" * 50)
        print("CLASSIFICATION METRICS (Like mAP95 / R^2)")
        print(f"Overall Accuracy: {accuracy:.1f}%")
        print(f"Mean Confidence : {(avg_confidence * 100):.1f}%")
        print(f"Fault Tolerance : {degraded_cases}/{total} cases gracefully degraded")
        print("-" * 50)
        print("LLM EFFICIENCY STATS")
        print(f"Vision Model    : {llm._vision_model}")
        print(f"Text Model      : {llm._text_model}")
        print(f"Total API Calls : {llm.stats['total_calls']}")
        print(f"Token Efficiency: {avg_tokens:.0f} tokens / case")
        print(f"Total Eval Time : {total_time_sec:.2f} seconds")
        print(f"Avg Latency     : {avg_time:.2f} seconds / case")
        print("="*50 + "\n")

        return {
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
            },
            "results": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Eval run failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
