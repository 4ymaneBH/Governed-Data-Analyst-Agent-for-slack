"""
Evaluation Runner - Governed Data Analyst Agent
Runs the 50-question evaluation suite and generates a report.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

AGENT_URL = "http://localhost:8002"
QUESTIONS_FILE = Path(__file__).parent / "questions.jsonl"
REPORT_FILE = Path(__file__).parent / "report.md"


async def run_evaluation():
    """Run the full evaluation suite."""
    
    print("=" * 60)
    print("Governed Data Analyst Agent - Evaluation Suite")
    print("=" * 60)
    
    # Load questions
    questions = []
    with open(QUESTIONS_FILE) as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    
    print(f"Loaded {len(questions)} questions")
    
    # Run evaluations
    results = []
    client = httpx.AsyncClient(timeout=120.0)
    
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] {q['question'][:50]}...")
        
        result = await evaluate_question(client, q)
        results.append(result)
        
        status = "✅" if result["pass"] else "❌"
        print(f"  {status} {result['decision']} (expected: {q['expected_decision']})")
    
    await client.aclose()
    
    # Generate report
    generate_report(questions, results)
    
    # Summary
    passed = sum(1 for r in results if r["pass"])
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{len(questions)} passed ({passed/len(questions)*100:.1f}%)")
    print(f"Report saved to: {REPORT_FILE}")


async def evaluate_question(client: httpx.AsyncClient, question: dict) -> dict:
    """Evaluate a single question."""
    
    start_time = time.time()
    
    try:
        response = await client.post(
            f"{AGENT_URL}/ask",
            json={
                "text": question["question"],
                "context": {
                    "user_id": f"eval_{question['test_role']}",
                    "slack_user_id": f"U_{question['test_role'].upper()}",
                    "role": question["test_role"],
                    "region": "NA" if question["test_role"] == "sales" else None
                },
                "request_id": f"eval_{question['id']}"
            }
        )
        
        latency = (time.time() - start_time) * 1000
        
        if response.status_code != 200:
            return {
                "id": question["id"],
                "pass": False,
                "decision": "ERROR",
                "latency_ms": latency,
                "error": f"HTTP {response.status_code}"
            }
        
        data = response.json()
        
        # Determine actual decision
        actual_decision = "ALLOW"
        if data.get("requires_approval"):
            actual_decision = "REQUIRE_APPROVAL"
        elif "Access denied" in str(data.get("answer_text", "")) or "denied" in str(data.get("answer_text", "")).lower():
            actual_decision = "DENY"
        
        # Check if passed
        passed = actual_decision == question["expected_decision"]
        
        return {
            "id": question["id"],
            "pass": passed,
            "decision": actual_decision,
            "expected": question["expected_decision"],
            "latency_ms": latency,
            "confidence": data.get("confidence", 0),
            "tool_count": len(data.get("tool_calls", []))
        }
        
    except Exception as e:
        return {
            "id": question["id"],
            "pass": False,
            "decision": "ERROR",
            "latency_ms": (time.time() - start_time) * 1000,
            "error": str(e)
        }


def generate_report(questions: list, results: list) -> None:
    """Generate markdown evaluation report."""
    
    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    
    # Calculate by category
    categories = {}
    for q, r in zip(questions, results):
        cat = q["category"]
        if cat not in categories:
            categories[cat] = {"passed": 0, "total": 0}
        categories[cat]["total"] += 1
        if r["pass"]:
            categories[cat]["passed"] += 1
    
    # Calculate metrics
    avg_latency = sum(r.get("latency_ms", 0) for r in results) / len(results)
    violations = sum(1 for r in results if not r["pass"] and r.get("expected") == "DENY" and r.get("decision") == "ALLOW")
    
    report = f"""# Evaluation Report

Generated: {datetime.now().isoformat()}

## Summary

| Metric | Value |
|--------|-------|
| Total Questions | {total} |
| Passed | {passed} |
| Failed | {total - passed} |
| Pass Rate | {passed/total*100:.1f}% |
| Avg Latency | {avg_latency:.0f}ms |
| Policy Violations | {violations} |

## Results by Category

| Category | Passed | Total | Rate |
|----------|--------|-------|------|
"""
    
    for cat, stats in sorted(categories.items()):
        rate = stats["passed"] / stats["total"] * 100
        report += f"| {cat} | {stats['passed']} | {stats['total']} | {rate:.0f}% |\n"
    
    report += """
## Detailed Results

| ID | Question | Role | Expected | Actual | Pass | Latency |
|----|----------|------|----------|--------|------|---------|
"""
    
    for q, r in zip(questions, results):
        status = "✅" if r["pass"] else "❌"
        report += f"| {q['id']} | {q['question'][:40]}... | {q['test_role']} | {q['expected_decision']} | {r['decision']} | {status} | {r.get('latency_ms', 0):.0f}ms |\n"
    
    if violations > 0:
        report += """
## ⚠️ Policy Violations

The following questions resulted in policy violations (expected DENY but got ALLOW):

"""
        for q, r in zip(questions, results):
            if not r["pass"] and r.get("expected") == "DENY" and r.get("decision") == "ALLOW":
                report += f"- **{q['id']}**: {q['question']}\n"
    
    with open(REPORT_FILE, "w") as f:
        f.write(report)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
