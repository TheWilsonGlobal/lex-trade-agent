"""Hermes ReAct / Plan-and-Solve Autonomous Compliance Agent.

Features:
- Hermes reasoning loop using structured XML/JSON syntax:
  <scratchpad>...</scratchpad>
  <tool_call>{"name": "...", "arguments": {...}}</tool_call>
- Native tool execution & dynamic error recovery.
- OpenAI-compatible LLM endpoint client with automatic MockLLMClient fallback.
- Episodic hybrid memory integration (scratchpad, SQLite audit trail, semantic search).
- Ready-to-run CLI demo for end-to-end export compliance evaluation.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Callable, Dict, List, Optional

# Ensure local packages can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure safe console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agent.llm_client import (
    BaseLLMClient,
    MockLLMClient,
    OpenAICompatibleClient,
    create_llm_client,
    load_env_file,
)
from agent.memory.hybrid_memory import AgentEpisodicMemory
from agent.tool_parser import extract_tool_calls, parse_ast_calls
from mcp_servers.compliance_mcp import lookup_hs_code, screen_entity, verify_dual_use


# ============================================================================
# Hermes Autonomous Agent
# ============================================================================

SYSTEM_PROMPT = """You are Hermes Trade Compliance Agent, an autonomous export control expert.
Follow the Hermes Plan-and-Solve reasoning loop.
Always structure your chain of thought inside <scratchpad>...</scratchpad>.

CRITICAL: You MUST execute audit checks by invoking tools. NEVER conclude without executing tools first.
When invoking tools, emit:
<|tool_call_start|>[screen_entity(name='...', country='...')]<|tool_call_end|>
or
<tool_call>{"name": "screen_entity", "arguments": {"name": "...", "country": "..."}}</tool_call>

Available Tools:
1. screen_entity(name: str, country: str) - Check denied parties, OFAC SDN, and sanctions lists.
2. lookup_hs_code(description: str) - Classify commodity and determine HS code.
3. verify_dual_use(product_spec: str) - Evaluate technical specifications against EU Annex I / Wassenaar dual-use thresholds.

Rules:
- Step 1: Call screen_entity(name=..., country=...) using the company name (NOT the shipment ID).
- Step 2: Call lookup_hs_code(description=...) to determine the HS code and ECCN classification.
- Step 3: Call verify_dual_use(product_spec=...) to check technical threshold limits.
- IMPORTANT: DO NOT re-invoke tools that have already been executed. Each tool only needs to be called ONCE.
- Once all tools have responded, output your complete FINAL AUDIT DETERMINATION with explicit status (DENIED, RESTRICTED, or CLEARED) and risk level (CRITICAL_HIGH, DUAL_USE_RESTRICTED, or LOW).
"""


class HermesAgent:
    """Autonomous compliance agent executing the Hermes ReAct loop."""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        memory: Optional[AgentEpisodicMemory] = None,
        max_turns: int = 8,
    ) -> None:
        self.llm = llm_client or create_llm_client()
        self.memory = memory or AgentEpisodicMemory()
        self.max_turns = max_turns
        self.tools: Dict[str, Callable[..., Any]] = {
            "screen_entity": screen_entity,
            "lookup_hs_code": lookup_hs_code,
            "verify_dual_use": verify_dual_use,
        }

    def _extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Delegate to tool_parser utility while maintaining class interface."""
        return extract_tool_calls(text, known_tools=self.tools)

    def _parse_ast_calls(self, expr_str: str, calls_out: List[Dict[str, Any]]) -> None:
        """Delegate to tool_parser utility while maintaining class interface."""
        parse_ast_calls(expr_str, calls_out, known_tools=self.tools)

    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool with error handling and fallback recovery."""
        if tool_name not in self.tools:
            return {"error": f"Tool '{tool_name}' not found."}

        try:
            func = self.tools[tool_name]
            return func(**args)
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}", "tool": tool_name}

    def run_compliance_audit(
        self,
        shipment_id: str,
        recipient_entity: str,
        destination_country: str,
        product_description: str,
        product_spec: str,
    ) -> Dict[str, Any]:
        """Run autonomous multi-step compliance evaluation for a shipment."""
        query_text = (
            f"Audit export to entity '{recipient_entity}' ({destination_country}). "
            f"Commodity: {product_description}. Specs: {product_spec}."
        )

        # 1. Check episodic memory for similar precedent
        precedents = self.memory.search_episodes(query_text, top_k=2)
        precedent_context = ""
        if precedents:
            precedent_context = (
                f"\n[Past Relevant Precedent Found (Similarity {precedents[0]['similarity']})]:\n"
                f"Shipment {precedents[0]['shipment_id']} - Risk: {precedents[0]['risk_level']}\n"
            )

        # 2. Setup conversation context
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT + precedent_context},
            {
                "role": "user",
                "content": (
                    f"Initiate compliance audit for Shipment ID: {shipment_id}\n"
                    f"Recipient: {recipient_entity}\n"
                    f"Destination Country: {destination_country}\n"
                    f"Product Description: {product_description}\n"
                    f"Technical Specifications: {product_spec}\n"
                ),
            },
        ]

        self.memory.add_scratchpad_message("system", SYSTEM_PROMPT)
        self.memory.add_scratchpad_message("user", messages[-1]["content"])

        recorded_tool_calls: List[Dict[str, Any]] = []
        action_plan: List[str] = []
        final_verdict: Dict[str, Any] = {}
        risk_level = "LOW"
        turn = 0

        print(f"\n{'='*70}")
        print(f"[START] Hermes Compliance Audit for Shipment [{shipment_id}]")
        print(f"{'='*70}")

        while turn < self.max_turns:
            turn += 1
            print(f"\n--- [Turn {turn}] Hermes Reasoning Loop ---")

            response = self.llm.complete(messages)
            self.memory.add_scratchpad_message("assistant", response)

            # Print scratchpad reasoning
            scratchpad_match = re.search(r"<scratchpad>(.*?)</scratchpad>", response, re.DOTALL)
            if scratchpad_match:
                reasoning = scratchpad_match.group(1).strip()
                action_plan.append(reasoning)
                print(f"[Scratchpad]\n{reasoning}\n")

            tool_calls = self._extract_tool_calls(response)

            if not tool_calls:
                # No tool calls; final synthesis reached
                print("[Verdict] Final Audit Determination Reached:")
                print(response)

                upper_resp = response.upper()

                # Focus risk parsing on the final Conclusion / Verdict section to avoid matching sub-checks (like Entity Screening: CLEARED)
                conclusion_markers = ["### CONCLUSION", "## CONCLUSION", "CONCLUSION:", "FINAL ACTION:", "OVERALL COMPLIANCE STATUS", "FINAL AUDIT DETERMINATION"]
                conclusion_text = upper_resp
                for marker in conclusion_markers:
                    idx = upper_resp.rfind(marker)
                    if idx != -1:
                        conclusion_text = upper_resp[idx:]
                        break

                has_dual_use_tool = any(
                    tc.get("name") == "verify_dual_use" and tc.get("result", {}).get("is_dual_use") is True
                    for tc in recorded_tool_calls
                )

                if any(w in conclusion_text for w in ["STATUS: DENIED", "DETERMINATION: CRITICAL_HIGH", "OFAC-SDN", "BLOCKED TRANSACTION"]):
                    risk_level = "CRITICAL_HIGH"
                elif any(w in conclusion_text for w in ["STATUS: RESTRICTED", "DUAL_USE_RESTRICTED", "PERMIT MANDATORY", "MANDATORY EXPORT AUTHORIZATION"]) or has_dual_use_tool:
                    if risk_level != "CRITICAL_HIGH":
                        risk_level = "DUAL_USE_RESTRICTED"
                elif any(w in conclusion_text for w in ["DETERMINATION: CLEARED", "STATUS: CLEARED", "NO LICENSE REQUIRED", "COMPLIANT"]):
                    if risk_level != "CRITICAL_HIGH" and not has_dual_use_tool:
                        risk_level = "LOW"

                final_verdict = {
                    "determination_summary": response,
                    "completed_turns": turn,
                }
                break

            tool_response_messages: List[str] = []
            already_executed_names = {c["name"] for c in recorded_tool_calls}

            for tc in tool_calls:
                t_name = tc.get("name", "")
                t_args = tc.get("arguments", {})

                if t_name not in self.tools:
                    tool_response_messages.append(
                        f"<tool_response>\n"
                        f'{{"tool": "{t_name}", "error": "Tool \'{t_name}\' does not exist. Available tools: screen_entity, lookup_hs_code, verify_dual_use"}}\n'
                        f"</tool_response>"
                    )
                    continue

                if t_name in already_executed_names:
                    prev_result = next((c["result"] for c in recorded_tool_calls if c["name"] == t_name), {})
                    tool_response_messages.append(
                        f"<tool_response>\n"
                        f'{{"tool": "{t_name}", "status": "ALREADY_COMPLETED", "previous_output": {json.dumps(prev_result)}, "note": "Tool \'{t_name}\' was already executed in a previous turn. Proceed to remaining required checks or synthesize your final determination."}}\n'
                        f"</tool_response>"
                    )
                    continue

                print(f"[Tool Call] Invoking: {t_name}({t_args})")

                t_result = self._execute_tool(t_name, t_args)
                recorded_tool_calls.append({"name": t_name, "arguments": t_args, "result": t_result})
                already_executed_names.add(t_name)

                self.memory.record_audit_step(shipment_id, f"tool_{t_name}", {"input": t_args, "output": t_result})

                if t_name == "screen_entity":
                    if t_result.get("risk_level") in ["CRITICAL_HIGH", "HIGH"] or t_result.get("action_required") == "TRANSACTION_DENIED_IMMEDIATELY":
                        risk_level = "CRITICAL_HIGH"
                elif t_name == "verify_dual_use":
                    if t_result.get("is_dual_use"):
                        if risk_level != "CRITICAL_HIGH":
                            risk_level = "DUAL_USE_RESTRICTED"

                tool_response_messages.append(
                    f"<tool_response>\n"
                    f'{{"tool": "{t_name}", "output": {json.dumps(t_result)}}}\n'
                    f"</tool_response>"
                )

            messages.append({"role": "assistant", "content": response})
            combined_tool_msg = "\n\n".join(tool_response_messages)
            messages.append({"role": "user", "content": combined_tool_msg})
            self.memory.add_scratchpad_message("user", combined_tool_msg)

        ep_id = self.memory.record_episode(
            shipment_id=shipment_id,
            query_text=query_text,
            action_plan=action_plan,
            tool_calls=recorded_tool_calls,
            verdict=final_verdict,
            risk_level=risk_level,
        )
        print(f"\n[Episodic Memory] Audit complete. Saved Episode ID #{ep_id} to persistent hybrid memory.")

        return {
            "shipment_id": shipment_id,
            "episode_id": ep_id,
            "risk_level": risk_level,
            "turns": turn,
            "tool_calls_executed": len(recorded_tool_calls),
            "tool_calls": recorded_tool_calls,
            "verdict": final_verdict,
        }


def run_cli_demo() -> None:
    """Run an end-to-end export shipment compliance audit demo."""
    agent = HermesAgent()

    sample_shipment = {
        "shipment_id": "EXP-2026-8941",
        "recipient_entity": "Vector Radiosystems",
        "destination_country": "RU",
        "product_description": "High frequency gallium nitride RF power amplifier modules for microwave links",
        "product_spec": "Solid state GaN power amplifier module, operating frequency 34.5 GHz, integrated AES-256 telemetry",
    }

    result = agent.run_compliance_audit(**sample_shipment)
    print("\n" + "=" * 70)
    print("[EXECUTION SUMMARY]")
    print(f"Shipment ID: {result['shipment_id']}")
    print(f"Risk Level:  {result['risk_level']}")
    print(f"Tool Calls:  {result['tool_calls_executed']}")
    print("=" * 70)


__all__ = [
    "BaseLLMClient",
    "OpenAICompatibleClient",
    "MockLLMClient",
    "load_env_file",
    "create_llm_client",
    "SYSTEM_PROMPT",
    "HermesAgent",
    "run_cli_demo",
]

if __name__ == "__main__":
    run_cli_demo()
