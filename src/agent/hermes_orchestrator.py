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

import ast
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

# Ensure local packages can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Ensure safe console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from agent.memory.hybrid_memory import AgentEpisodicMemory
from mcp_servers.compliance_mcp import lookup_hs_code, screen_entity, verify_dual_use


# ============================================================================
# LLM Client Abstraction (OpenAI-Compatible + MockLLM Fallback)
# ============================================================================

class BaseLLMClient:
    """Abstract base class for LLM inference clients."""

    def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        raise NotImplementedError


class OpenAICompatibleClient(BaseLLMClient):
    """Client for local Vulkan/llama-server (Hermes 3 GGUF) or OpenRouter."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "local",
        model: str = "hermes-3-llama-3.1-8b",
        timeout: float = 90.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def is_available(self) -> bool:
        """Ping endpoint to verify if server is responsive."""
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/models")
                return res.status_code == 200
        except Exception:
            return False

    def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


class MockLLMClient(BaseLLMClient):
    """
    Deterministic Hermes Mock LLM engine.
    Simulates genuine ReAct reasoning steps, dynamic error recovery,
    and tool invocations for compliance pipelines without requiring a live model server.
    """

    def __init__(self) -> None:
        self.step_counter: int = 0

    def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        self.step_counter += 1
        last_message = messages[-1]["content"] if messages else ""

        # Extract context attributes from first user message
        recipient = "Unknown Entity"
        country = ""
        description = "electronic equipment"
        spec = ""

        for m in messages:
            if m.get("role") == "user":
                content = m.get("content", "")
                r_match = re.search(r"Recipient:\s*(.*?)\n", content)
                c_match = re.search(r"Destination Country:\s*(.*?)\n", content)
                d_match = re.search(r"Product Description:\s*(.*?)\n", content)
                s_match = re.search(r"Technical Specifications:\s*(.*?)\n", content)
                if r_match:
                    recipient = r_match.group(1).strip()
                if c_match:
                    country = c_match.group(1).strip()
                if d_match:
                    description = d_match.group(1).strip()
                if s_match:
                    spec = s_match.group(1).strip()

        # Check conversation history for completed tools
        history_text = " ".join(m.get("content", "") for m in messages)
        has_screened = "tool_screen_entity" in history_text or '"tool": "screen_entity"' in history_text
        has_looked_up_hs = "tool_lookup_hs_code" in history_text or '"tool": "lookup_hs_code"' in history_text
        has_verified_dual_use = "tool_verify_dual_use" in history_text or '"tool": "verify_dual_use"' in history_text

        # 1. Error Recovery check: If screen_entity yielded POTENTIAL_MATCH_REVIEW
        if "<tool_response>" in last_message and "POTENTIAL_MATCH_REVIEW" in last_message:
            return (
                "<scratchpad>\n"
                f"The initial screening for '{recipient}' returned an ambiguous score (POTENTIAL_MATCH_REVIEW). "
                "Executing dynamic recovery plan: query normalized trade aliases.\n"
                "</scratchpad>\n"
                f'<tool_call>{{"name": "screen_entity", "arguments": {{"name": "{recipient.split()[0]}", "country": "{country}"}}}}</tool_call>'
            )

        # 2. Step 1: Initial Screen Entity
        if not has_screened:
            return (
                "<scratchpad>\n"
                f"Initiating compliance audit for recipient '{recipient}' in country '{country}'. "
                "Step 1: Screen recipient against OFAC SDN and EU Consolidated sanctions lists.\n"
                "</scratchpad>\n"
                f'<tool_call>{{"name": "screen_entity", "arguments": {{"name": "{recipient}", "country": "{country}"}}}}</tool_call>'
            )

        # 3. Step 2: HS Code Classification
        if not has_looked_up_hs:
            return (
                "<scratchpad>\n"
                f"Sanctions check complete. Step 2: Determine Harmonized System (HS) code for commodity '{description}'.\n"
                "</scratchpad>\n"
                f'<tool_call>{{"name": "lookup_hs_code", "arguments": {{"description": "{description}"}}}}</tool_call>'
            )

        # 4. Step 3: Technical Dual-Use Verification
        if not has_verified_dual_use:
            # Check if commercial consumer item without technical specs
            is_consumer = any(w in description.lower() for w in ["laptop", "tablet", "consumer", "notebook"]) and not any(
                w in spec.lower() for w in ["ghz", "aes-256", "radiation", "encryption"]
            )
            if not is_consumer and spec:
                return (
                    "<scratchpad>\n"
                    f"HS code resolved. Step 3: Performing technical parameter audit under EU Annex I / Wassenaar for specs: '{spec}'.\n"
                    "</scratchpad>\n"
                    f'<tool_call>{{"name": "verify_dual_use", "arguments": {{"product_spec": "{spec}"}}}}</tool_call>'
                )

        # 5. Final Step: Synthesis & Audit Determination
        # Analyze overall risk based on tool outputs in history
        if "CRITICAL_HIGH" in history_text or "OFAC-SDN" in history_text or "CMIC" in history_text:
            risk_summary = "CRITICAL_HIGH - Identified on Denied Persons / Sanctions list. HUMAN_ESCALATION_REQUIRED."
            action_summary = "TRANSACTION BLOCKED & ESCALATED TO COMPLIANCE DIRECTOR."
        elif "is_dual_use\": true" in history_text or "3A001" in history_text or "5A002" in history_text:
            risk_summary = "DUAL_USE_RESTRICTED - Technical parameters exceed commercial de-minimis."
            action_summary = "EXPORT PERMIT REQUIRED PRIOR TO CUSTOMS CLEARANCE."
        else:
            risk_summary = "CLEARED / LOW RISK - Commercial item eligible for standard export."
            action_summary = "STANDARD COMMERCIAL EXPORT CLEARED (NLR - No License Required)."

        return (
            "<scratchpad>\n"
            "All compliance checks completed. Synthesizing holistic export determination across sanctions, HS tariff, and dual-use controls.\n"
            "</scratchpad>\n"
            "### COMPLIANCE AUDIT DETERMINATION\n"
            f"- **Recipient Status**: {risk_summary}\n"
            f"- **Commodity**: {description}\n"
            f"- **Classification**: Evaluated under EU Dual-Use Regulation Annex I & Wassenaar Arrangement.\n"
            f"- **Final Action**: {action_summary}"
        )


def load_env_file() -> None:
    """Load key-value pairs from .env file into os.environ if not already set."""
    # Check repository root (.env)
    candidate_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
    ]
    for env_file in candidate_paths:
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k:
                                os.environ[k] = v
                break
            except Exception:
                pass


def create_llm_client(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    force_mock: bool = False,
) -> BaseLLMClient:
    """Factory creating OpenAICompatibleClient if available, otherwise MockLLMClient."""
    load_env_file()

    if force_mock or os.getenv("FORCE_MOCK_LLM", "false").lower() == "true":
        return MockLLMClient()

    resolved_base_url = (
        base_url
        or os.getenv("LLM_API_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "http://localhost:8000/v1"
    )
    resolved_api_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "local"
    resolved_model = model or os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "hermes-3-llama-3.1-8b"

    client = OpenAICompatibleClient(base_url=resolved_base_url, api_key=resolved_api_key, model=resolved_model)
    if client.is_available():
        print(f"[HermesOrchestrator] Connected to active LLM endpoint at {resolved_base_url} (model: {resolved_model})")
        return client

    print(f"[HermesOrchestrator] No active endpoint detected at {resolved_base_url}. Falling back to MockLLMClient.")
    return MockLLMClient()


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
        """
        Extract tool calls from multiple model output formats:
        1. Standard XML: <tool_call>{"name": ..., "arguments": ...}</tool_call>
        2. Liquid / Hermes special tokens: <|tool_call_start|>[func(arg='val')]<|tool_call_end|>
        3. Raw JSON: <tool_call>[{...}]</tool_call> or <|tool_call_start|>[{...}]<|tool_call_end|>
        4. Fallback python call expressions: screen_entity(...), etc.
        """
        calls: List[Dict[str, Any]] = []

        # 1. XML format <tool_call>...</tool_call>
        xml_matches = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
        for m in xml_matches:
            m = m.strip()
            # Try JSON parsing
            try:
                parsed = json.loads(m)
                if isinstance(parsed, list):
                    calls.extend(parsed)
                elif isinstance(parsed, dict):
                    calls.append(parsed)
                continue
            except json.JSONDecodeError:
                pass
            # Try regex cleanup for single quotes
            try:
                cleaned = m.replace("'", '"')
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    calls.extend(parsed)
                elif isinstance(parsed, dict):
                    calls.append(parsed)
                continue
            except Exception:
                pass
            # Try Python AST
            self._parse_ast_calls(m, calls)

        # 2. Liquid / Hermes special tokens: <|tool_call_start|>(.*?)<|tool_call_end|>
        lfm_matches = re.findall(r"<\|tool_call_start\|>\s*(.*?)\s*(?:<\|tool_call_end\|>|$)", text, re.DOTALL)
        for block in lfm_matches:
            block = block.strip()
            # Case A: JSON format
            if block.startswith("{") or block.startswith("["):
                try:
                    parsed = json.loads(block)
                    if isinstance(parsed, list):
                        calls.extend(parsed)
                    elif isinstance(parsed, dict):
                        calls.append(parsed)
                    continue
                except Exception:
                    pass
            # Case B: Python-style expression list: [func(arg=val), ...]
            self._parse_ast_calls(block, calls)

        # 3. Direct pattern fallback if no calls extracted yet
        if not calls:
            direct_matches = re.findall(
                r"(\b(?:screen_entity|lookup_hs_code|verify_dual_use))\((.*?)\)", text, re.DOTALL
            )
            for fname, args_str in direct_matches:
                kv_matches = re.findall(r"(\w+)\s*=\s*['\"](.*?)['\"]", args_str)
                if kv_matches:
                    calls.append({"name": fname, "arguments": dict(kv_matches)})

        # Validate extracted calls
        valid_calls = []
        for c in calls:
            if isinstance(c, dict) and "name" in c:
                name = c["name"]
                args = c.get("arguments", {})
                if not isinstance(args, dict):
                    args = {}
                valid_calls.append({"name": name, "arguments": args})

        return valid_calls

    def _parse_ast_calls(self, expr_str: str, calls_out: List[Dict[str, Any]]) -> None:
        """Parse Python-style AST expressions like [screen_entity(name='...', country='...')]"""
        try:
            tree = ast.parse(expr_str.strip(), mode="eval")
            nodes = []
            if isinstance(tree.body, ast.List):
                nodes = tree.body.elts
            elif isinstance(tree.body, ast.Call):
                nodes = [tree.body]
            elif isinstance(tree.body, ast.Tuple):
                nodes = tree.body.elts

            for node in nodes:
                if isinstance(node, ast.Call):
                    func_name = node.func.id if isinstance(node.func, ast.Name) else str(node.func)
                    kwargs = {}
                    for kw in node.keywords:
                        try:
                            kwargs[kw.arg] = ast.literal_eval(kw.value)
                        except Exception:
                            kwargs[kw.arg] = ast.unparse(kw.value) if hasattr(ast, "unparse") else str(kw.value)
                    calls_out.append({"name": func_name, "arguments": kwargs})
        except Exception:
            # Fallback regex if AST parsing fails
            func_matches = re.finditer(r"(\b\w+)\((.*?)\)", expr_str)
            for fm in func_matches:
                fname = fm.group(1)
                args_str = fm.group(2)
                kv_matches = re.findall(r"(\w+)\s*=\s*['\"](.*?)['\"]", args_str)
                if kv_matches and fname in self.tools:
                    calls_out.append({"name": fname, "arguments": dict(kv_matches)})

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
        """
        Run autonomous multi-step compliance evaluation for a shipment.
        """
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

                # Infer risk level from final synthesis text if not already escalated
                upper_resp = response.upper()
                if any(w in upper_resp for w in ["DENIED", "CRITICAL_HIGH", "OFAC-SDN", "BLOCKED", "SANCTIONED", "RED FLAG"]):
                    risk_level = "CRITICAL_HIGH"
                elif any(w in upper_resp for w in ["DUAL_USE_RESTRICTED", "DUAL-USE", "PERMIT MANDATORY", "ANNEX I"]):
                    if risk_level != "CRITICAL_HIGH":
                        risk_level = "DUAL_USE_RESTRICTED"

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

                # Validate tool existence
                if t_name not in self.tools:
                    tool_response_messages.append(
                        f"<tool_response>\n"
                        f'{{"tool": "{t_name}", "error": "Tool \'{t_name}\' does not exist. Available tools: screen_entity, lookup_hs_code, verify_dual_use"}}\n'
                        f"</tool_response>"
                    )
                    continue

                # De-duplicate: avoid re-running same tool if already completed
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

                # Log step in memory
                self.memory.record_audit_step(shipment_id, f"tool_{t_name}", {"input": t_args, "output": t_result})

                # Check risk triggers
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

        # Record completed episode in persistent memory
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


# ============================================================================
# CLI Demo
# ============================================================================

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


if __name__ == "__main__":
    run_cli_demo()
