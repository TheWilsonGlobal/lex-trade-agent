"""End-to-end test suite for Hermes compliance orchestrator and episodic memory.

Verifies:
1. Complete Hermes reasoning loop with MockLLM fallback (no API key required).
2. Dynamic error recovery handling.
3. Structured XML tool call extraction and dispatch.
4. Episodic memory audit logging and semantic precedent retrieval.
"""

from __future__ import annotations

import json
import pytest
from agent.hermes_orchestrator import HermesAgent, MockLLMClient
from agent.memory.hybrid_memory import AgentEpisodicMemory


class TestHermesOrchestrator:
    """Test suite for autonomous agent orchestrator."""

    def test_mock_llm_orchestrator_end_to_end_sanctioned(self) -> None:
        """Verifies full execution loop without requiring external model endpoint."""
        memory = AgentEpisodicMemory(db_path=":memory:")
        agent = HermesAgent(llm_client=MockLLMClient(), memory=memory)

        shipment = {
            "shipment_id": "TEST-SHP-8812",
            "recipient_entity": "CJSC Vektor Radiosystems",
            "destination_country": "RU",
            "product_description": "Microwave power amplification module",
            "product_spec": "36.0 GHz operating frequency, AES-256",
        }

        result = agent.run_compliance_audit(**shipment)

        assert result["shipment_id"] == "TEST-SHP-8812"
        assert result["risk_level"] == "CRITICAL_HIGH"
        assert result["tool_calls_executed"] >= 2
        assert result["episode_id"] > 0
        assert "determination_summary" in result["verdict"]

        # Verify audit logs in episodic memory
        audit_trail = memory.get_audit_trail("TEST-SHP-8812")
        assert len(audit_trail) >= 2
        step_names = [a["step_name"] for a in audit_trail]
        assert "tool_screen_entity" in step_names

    def test_episodic_memory_semantic_retrieval(self) -> None:
        """Verifies semantic similarity lookup over past audit episodes."""
        memory = AgentEpisodicMemory(db_path=":memory:")

        # Record past episode
        ep1_id = memory.record_episode(
            shipment_id="HIST-001",
            query_text="Export GaN RF amplifier 34 GHz to Vektor Russia",
            action_plan=["Screen Vektor", "Classify RF amplifier"],
            tool_calls=[{"name": "screen_entity"}],
            verdict={"status": "BLOCKED"},
            risk_level="CRITICAL_HIGH",
        )

        ep2_id = memory.record_episode(
            shipment_id="HIST-002",
            query_text="Commercial laptop computers to Germany",
            action_plan=["Screen Nordic", "Classify laptop"],
            tool_calls=[{"name": "lookup_hs_code"}],
            verdict={"status": "CLEARED"},
            risk_level="LOW",
        )

        # Search for semantically related query
        results = memory.search_episodes("GaN microwave amplifier RF Russia", top_k=2)
        assert len(results) > 0
        assert results[0]["id"] == ep1_id
        assert results[0]["risk_level"] == "CRITICAL_HIGH"
        assert results[0]["similarity"] > 0.15

    def test_dynamic_error_recovery_flow(self) -> None:
        """Verifies agent handles ambiguous entity review gracefully."""
        memory = AgentEpisodicMemory(db_path=":memory:")
        agent = HermesAgent(llm_client=MockLLMClient(), memory=memory)

        # Execute check for an entity requiring review
        result = agent.run_compliance_audit(
            shipment_id="TEST-AMBIGUOUS-01",
            recipient_entity="Vector Radiosystems",
            destination_country="RU",
            product_description="High frequency amplifier",
            product_spec="33 GHz GaN",
        )

        assert result["risk_level"] == "CRITICAL_HIGH"
        assert result["tool_calls_executed"] >= 2
