"""Unit tests for compliance FastMCP tools.

Verifies:
1. Fuzzy sanctions matching confidence & human escalation thresholds (score >= 85%).
2. HS Code classification accuracy and dual-use flags.
3. Dual-use parameter verification against EU Annex I / Wassenaar thresholds.
"""

from __future__ import annotations

import pytest
from mcp_servers.compliance_mcp import lookup_hs_code, screen_entity, verify_dual_use


class TestSanctionsScreeningTool:
    """Test suite for screen_entity tool."""

    def test_direct_sanctions_match_triggers_escalation(self) -> None:
        result = screen_entity(name="CJSC Vektor Radiosystems", country="RU")
        assert result["highest_confidence"] >= 85.0
        assert result["risk_level"] == "CRITICAL_HIGH"
        assert result["status"] == "HUMAN_ESCALATION_REQUIRED"
        assert result["matched_record"] is not None
        assert "Vektor" in result["matched_record"]["name"]

    def test_alias_sanctions_match(self) -> None:
        result = screen_entity(name="Vector Radiosystems", country="RU")
        assert result["highest_confidence"] >= 85.0
        assert result["status"] == "HUMAN_ESCALATION_REQUIRED"

    def test_clean_entity_is_cleared(self) -> None:
        result = screen_entity(name="Nordic Eco Logistics Oy", country="FI")
        assert result["highest_confidence"] < 60.0
        assert result["risk_level"] == "LOW"
        assert result["status"] == "CLEARED"
        assert result["matched_record"] is None

    def test_threshold_borderline_potential_review(self) -> None:
        # Entity sharing partial token with "Integral Minsk"
        result = screen_entity(name="Integral Automation Systems", country="DE")
        # Should be below 85% but above or around low threshold
        assert result["status"] in ["POTENTIAL_MATCH_REVIEW", "CLEARED"]
        if result["highest_confidence"] >= 85.0:
            assert result["status"] == "HUMAN_ESCALATION_REQUIRED"


class TestHSCodeLookupTool:
    """Test suite for lookup_hs_code tool."""

    def test_semiconductor_processor_classification(self) -> None:
        result = lookup_hs_code("high performance microcontroller microprocessor chip")
        assert result["matched_hs_code"] == "8542.31"
        assert result["dual_use_indicator"] is True
        assert "3A001.a" in result["eccn_mapping"]

    def test_rf_microwave_amplifier_classification(self) -> None:
        result = lookup_hs_code("RF microwave signal generator and high frequency amplifier")
        assert result["matched_hs_code"] == "8543.70"
        assert result["dual_use_indicator"] is True
        assert "3A001.b" in result["eccn_mapping"]

    def test_commercial_laptop_classification(self) -> None:
        result = lookup_hs_code("portable commercial notebook laptop computer")
        assert result["matched_hs_code"] == "8471.30"
        assert result["dual_use_indicator"] is False
        assert "EAR99" in result["eccn_mapping"]


class TestDualUseVerificationTool:
    """Test suite for verify_dual_use technical parameter auditor."""

    def test_category_3_frequency_threshold_trigger(self) -> None:
        # Exceeds 31.8 GHz threshold
        result = verify_dual_use("Gallium Nitride RF amplifier with 35.0 GHz operating frequency")
        assert result["is_dual_use"] is True
        assert result["matched_eccn"] == "3A001.b.2"
        assert result["licensing_required"] is True
        assert any("31.8 GHz" in finding for finding in result["threshold_findings"])

    def test_category_5_cryptographic_key_length_trigger(self) -> None:
        # Exceeds 56-bit symmetric threshold
        result = verify_dual_use("Commercial telemetry transmitter with AES 256-bit hardware encryption")
        assert result["is_dual_use"] is True
        assert result["matched_eccn"] == "5A002.a.1"
        assert result["licensing_required"] is True
        assert any("256 bits" in finding for finding in result["threshold_findings"])

    def test_category_6_thermal_framerate_trigger(self) -> None:
        # Exceeds 9 Hz frame rate
        result = verify_dual_use("Infrared thermal imaging camera with 60 Hz frame rate")
        assert result["is_dual_use"] is True
        assert result["matched_eccn"] == "6A003.b.4"
        assert result["licensing_required"] is True

    def test_standard_commercial_parameters_cleared(self) -> None:
        result = verify_dual_use("Standard commercial Bluetooth 5.0 sensor operating at 2.4 GHz with standard pairing")
        assert result["is_dual_use"] is False
        assert result["matched_eccn"] == "EAR99"
        assert result["licensing_required"] is False
