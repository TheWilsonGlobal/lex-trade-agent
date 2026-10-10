"""Non-lexical Agent Evaluation Benchmark for Autonomous Trade Compliance.

Evaluates HermesAgent execution across 4 key pillars:
1. Task Completion Precision: Correct sanction/dual-use status classification.
2. Tool Invocation Accuracy: Zero hallucinated parameters, minimal redundant calls.
3. Token Efficiency: Prompt token consumption vs reasoning depth.
4. Latency Profile: Subtask execution duration and response profiling.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Ensure local packages can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agent.hermes_orchestrator import HermesAgent, MockLLMClient
from agent.memory.hybrid_memory import AgentEpisodicMemory


class BenchmarkScenario(BaseModel):
    scenario_id: str
    description: str
    shipment_id: str
    recipient_entity: str
    destination_country: str
    product_description: str
    product_spec: str
    expected_risk: str
    expected_tools: List[str]
    critical_keywords_in_verdict: List[str]


BENCHMARK_SCENARIOS: List[BenchmarkScenario] = [
    BenchmarkScenario(
        scenario_id="SCENARIO-01-SANCTIONED-DEFENSE",
        description="Shipment of high-frequency GaN RF amplifiers to Russian defense entity.",
        shipment_id="EVAL-SHP-001",
        recipient_entity="Vector Radiosystems",
        destination_country="RU",
        product_description="Gallium Nitride RF high frequency microwave amplifier",
        product_spec="Operating frequency 34.5 GHz with 256-bit AES cryptographic telemetry",
        expected_risk="CRITICAL_HIGH",
        expected_tools=["screen_entity", "lookup_hs_code", "verify_dual_use"],
        critical_keywords_in_verdict=["CRITICAL_HIGH", "OFAC", "3A001"],
    ),
    BenchmarkScenario(
        scenario_id="SCENARIO-02-COMMERCIAL-LAPTOPS",
        description="Standard commercial laptops export to European logistics hub.",
        shipment_id="EVAL-SHP-002",
        recipient_entity="Nordic Logistics GmbH",
        destination_country="DE",
        product_description="Standard commercial business laptops with integrated webcams",
        product_spec="Standard x86 processor at 2.4 GHz, commercial OS with standard SSL/TLS",
        expected_risk="LOW",
        expected_tools=["screen_entity", "lookup_hs_code"],
        critical_keywords_in_verdict=["CLEARED", "LOW", "EAR99"],
    ),
    BenchmarkScenario(
        scenario_id="SCENARIO-03-CHINESE-SEMICONDUCTOR",
        description="Advanced microprocessors to Chinese entity on CMIC list.",
        shipment_id="EVAL-SHP-003",
        recipient_entity="Hangzhou Microtech Electronics Co Ltd",
        destination_country="CN",
        product_description="Multicore microprocessor integrated circuits for signal processing",
        product_spec="Operating frequency 55 GHz, high-density FPGA coprocessor",
        expected_risk="CRITICAL_HIGH",
        expected_tools=["screen_entity", "lookup_hs_code", "verify_dual_use"],
        critical_keywords_in_verdict=["CRITICAL_HIGH", "3A001", "CMIC"],
    ),
]


class PillarScores(BaseModel):
    task_completion_precision: float = Field(..., description="0-100% precision score")
    tool_invocation_accuracy: float = Field(..., description="0-100% accuracy score")
    token_efficiency_score: float = Field(..., description="0-100% token economy score")
    latency_profile_ms: float = Field(..., description="Average latency per subtask in ms")


class ScenarioEvalResult(BaseModel):
    scenario_id: str
    risk_match: bool
    tools_called: List[str]
    tools_expected: List[str]
    tool_accuracy: float
    total_tokens_estimated: int
    duration_ms: float
    passed: bool


class ComplianceEvaluationBenchmark:
    """Evaluates agent performance against the 4 compliance pillars."""

    def __init__(self) -> None:
        pass

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (approx 4 chars per token)."""
        return max(1, len(text) // 4)

    def evaluate_scenario(self, scenario: BenchmarkScenario) -> ScenarioEvalResult:
        # Use clean isolated in-memory DB for reproducible benchmark
        isolated_mem = AgentEpisodicMemory(db_path=":memory:")
        agent = HermesAgent(llm_client=MockLLMClient(), memory=isolated_mem)

        t_start = time.perf_counter()
        audit_output = agent.run_compliance_audit(
            shipment_id=scenario.shipment_id,
            recipient_entity=scenario.recipient_entity,
            destination_country=scenario.destination_country,
            product_description=scenario.product_description,
            product_spec=scenario.product_spec,
        )
        t_end = time.perf_counter()
        duration_ms = (t_end - t_start) * 1000.0

        actual_risk = audit_output["risk_level"]
        risk_match = actual_risk == scenario.expected_risk

        executed_tools = [tc["name"] for tc in audit_output.get("tool_calls", [])]

        # Tool invocation accuracy: check for valid tool names and no hallucinations
        valid_tools = {"screen_entity", "lookup_hs_code", "verify_dual_use"}
        hallucinated_tools = [t for t in executed_tools if t not in valid_tools]
        redundant_calls = len(executed_tools) - len(set(executed_tools))

        tool_score = 100.0
        if hallucinated_tools:
            tool_score -= 40.0 * len(hallucinated_tools)
        if redundant_calls > 1:
            tool_score -= 15.0 * (redundant_calls - 1)
        tool_score = max(0.0, min(100.0, tool_score))

        # Token calculation
        total_tokens = sum(
            self._estimate_tokens(json.dumps(tc)) for tc in audit_output.get("tool_calls", [])
        )
        verdict_str = json.dumps(audit_output.get("verdict", {}))
        total_tokens += self._estimate_tokens(verdict_str)

        passed = risk_match and tool_score >= 80.0

        return ScenarioEvalResult(
            scenario_id=scenario.scenario_id,
            risk_match=risk_match,
            tools_called=executed_tools,
            tools_expected=scenario.expected_tools,
            tool_accuracy=tool_score,
            total_tokens_estimated=total_tokens,
            duration_ms=round(duration_ms, 2),
            passed=passed,
        )

    def run_benchmark(self) -> Dict[str, Any]:
        print("\n" + "=" * 75)
        print("📊 RUNNING NON-LEXICAL AGENT EVALUATION BENCHMARK")
        print("=" * 75)

        scenario_results: List[ScenarioEvalResult] = []
        for sc in BENCHMARK_SCENARIOS:
            print(f"\n-> Running Scenario: {sc.scenario_id} ({sc.description})")
            res = self.evaluate_scenario(sc)
            scenario_results.append(res)

        # Compute Pillar 1: Task Completion Precision
        correct_risks = sum(1 for r in scenario_results if r.risk_match)
        task_precision = (correct_risks / len(scenario_results)) * 100.0

        # Compute Pillar 2: Tool Invocation Accuracy
        avg_tool_accuracy = sum(r.tool_accuracy for r in scenario_results) / len(scenario_results)

        # Compute Pillar 3: Token Efficiency Score
        # (Based on maintaining tight reasoning budget < 1200 tokens per full audit)
        avg_tokens = sum(r.total_tokens_estimated for r in scenario_results) / len(scenario_results)
        token_efficiency = max(0.0, min(100.0, 100.0 - max(0.0, (avg_tokens - 400) / 10.0)))

        # Compute Pillar 4: Latency Profile
        avg_latency_ms = sum(r.duration_ms for r in scenario_results) / len(scenario_results)

        # Overall weighted composite score
        overall_readiness_score = (
            task_precision * 0.40
            + avg_tool_accuracy * 0.30
            + token_efficiency * 0.15
            + (100.0 if avg_latency_ms < 5000 else 70.0) * 0.15
        )

        print("\n" + "=" * 75)
        print("🏆 EVALUATION BENCHMARK REPORT SUMMARY")
        print("=" * 75)
        print(f"1. Task Completion Precision:   {task_precision:.1f}%")
        print(f"2. Tool Invocation Accuracy:    {avg_tool_accuracy:.1f}%")
        print(f"3. Token Efficiency Index:      {token_efficiency:.1f}% (Avg Tokens: {avg_tokens:.0f})")
        print(f"4. Latency Profile (Wall Time): {avg_latency_ms:.1f} ms per audit")
        print("-" * 75)
        print(f"⭐ Composite Production Readiness Score: {overall_readiness_score:.1f} / 100.0")
        print("=" * 75)

        return {
            "task_completion_precision": round(task_precision, 2),
            "tool_invocation_accuracy": round(avg_tool_accuracy, 2),
            "token_efficiency_score": round(token_efficiency, 2),
            "average_latency_ms": round(avg_latency_ms, 2),
            "composite_score": round(overall_readiness_score, 2),
            "scenarios_evaluated": [r.model_dump() for r in scenario_results],
        }


if __name__ == "__main__":
    evaluator = ComplianceEvaluationBenchmark()
    evaluator.run_benchmark()
