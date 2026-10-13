"""LLM client abstractions for Hermes Trade Compliance Agent.

Supports OpenAI-compatible endpoints (local Vulkan llama-server, vLLM, OpenRouter, LFM)
and deterministic MockLLMClient fallback for offline environments and testing.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional
import httpx


class BaseLLMClient:
    """Abstract base class for LLM inference clients."""

    def complete(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        raise NotImplementedError


class OpenAICompatibleClient(BaseLLMClient):
    """Client for local Vulkan/llama-server (Hermes 3 GGUF, LFM 2.5) or OpenRouter."""

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
    """Deterministic Hermes Mock LLM engine.

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
        tool_responses_text = " ".join(
            m.get("content", "") for m in messages if "<tool_response>" in m.get("content", "")
        )
        if any(k in tool_responses_text for k in ["CRITICAL_HIGH", "OFAC-SDN", "CMIC-EO13959", "HUMAN_ESCALATION_REQUIRED"]):
            risk_summary = "CRITICAL_HIGH - Identified on Denied Persons / Sanctions list. HUMAN_ESCALATION_REQUIRED."
            action_summary = "TRANSACTION BLOCKED & ESCALATED TO COMPLIANCE DIRECTOR."
        elif '"is_dual_use": true' in tool_responses_text or "3A001" in tool_responses_text or "5A002" in tool_responses_text:
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
