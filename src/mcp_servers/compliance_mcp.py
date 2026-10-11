"""Compliance MCP Server.

Provides FastMCP tools for trade compliance, sanctions screening,
Harmonized System (HS) code classification, and dual-use technical verification
under EU Dual-Use Regulation (Annex I) and the Wassenaar Arrangement.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional

from mcp_servers.fuzzy_matcher import calculate_fuzzy_score, normalize_string
from mcp_servers.models_and_data import (
    MOCK_HS_DATABASE,
    MOCK_SANCTIONS_DB,
    LookupHSCodeResponse,
    ScreenEntityResponse,
    VerifyDualUseResponse,
)

# Aliases for backward compatibility
_normalize_string = normalize_string
_calculate_fuzzy_score = calculate_fuzzy_score

# Support mcp 1.x, mcp 2.x, or standalone fallback
try:
    try:
        from mcp.server.fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError):
        from mcp.server.mcpserver import MCPServer as FastMCP
except Exception:  # Fallback lightweight dummy FastMCP for isolated environments
    class FastMCP:  # type: ignore
        def __init__(self, name: str = "compliance-mcp", **kwargs: Any) -> None:
            self.name = name
            self.tools: Dict[str, Any] = {}

        def tool(self, name: Optional[str] = None):
            def decorator(fn):
                tool_name = name or fn.__name__
                self.tools[tool_name] = fn
                return fn
            return decorator

        def run(self, *args: Any, **kwargs: Any) -> None:
            print(f"[{self.name}] Running mock FastMCP server")


mcp = FastMCP("compliance-mcp")


# ============================================================================
# FastMCP Production-Grade Compliance Tools
# ============================================================================

@mcp.tool(name="screen_entity")
def screen_entity(name: str, country: str = "") -> Dict[str, Any]:
    """
    Performs fuzzy matching against embedded mock OFAC SDN and EU consolidated sanctions data.

    Calculates fuzzy match confidence (0-100%).
    Flags high risk if score >= 85%, triggering a "HUMAN_ESCALATION_REQUIRED" status.
    """
    best_score = 0.0
    best_match: Optional[Dict[str, Any]] = None
    matched_via_alias = False

    for record in MOCK_SANCTIONS_DB:
        # Check primary name
        score_name = calculate_fuzzy_score(name, record["name"])

        # Country correlation bonus/penalty
        country_match = False
        if country and record.get("country"):
            if country.strip().upper() == record["country"].strip().upper():
                country_match = True
                score_name = min(100.0, score_name + 5.0)

        if score_name > best_score:
            best_score = score_name
            best_match = record
            matched_via_alias = False

        # Check aliases
        for alias in record.get("aliases", []):
            score_alias = calculate_fuzzy_score(name, alias)
            if country_match:
                score_alias = min(100.0, score_alias + 5.0)

            if score_alias > best_score:
                best_score = score_alias
                best_match = record
                matched_via_alias = True

    # Determine status & risk level
    if best_score >= 85.0:
        risk_level = "CRITICAL_HIGH"
        status = "HUMAN_ESCALATION_REQUIRED"
        reasoning = (
            f"High confidence sanctions match ({best_score}%) with {best_match['name']} "
            f"under program {best_match.get('program')}. Immediate human escalation and transaction hold mandated."
        )
    elif best_score >= 60.0:
        risk_level = "MEDIUM"
        status = "POTENTIAL_MATCH_REVIEW"
        reasoning = (
            f"Moderate fuzzy match score ({best_score}%) with {best_match['name']}. "
            f"Secondary documentation and KYC re-verification recommended."
        )
    else:
        risk_level = "LOW"
        status = "CLEARED"
        reasoning = (
            f"No significant matching records on OFAC SDN or EU Consolidated lists. "
            f"Highest match confidence was {best_score}%."
        )

    response = ScreenEntityResponse(
        query_entity=name,
        query_country=country,
        highest_confidence=best_score,
        matched_record=best_match if best_score >= 60.0 else None,
        risk_level=risk_level,
        status=status,
        reasoning=reasoning,
    )
    return response.model_dump()


@mcp.tool(name="lookup_hs_code")
def lookup_hs_code(description: str) -> Dict[str, Any]:
    """
    Matches product descriptions to 6-digit Harmonized System (HS) codes.
    Returns tariff classifications, dual-use indicator, and licensing prerequisites.
    """
    query_norm = normalize_string(description)

    best_entry: Optional[Dict[str, Any]] = None
    best_score = -1.0

    for item in MOCK_HS_DATABASE:
        score = 0.0
        # Check keyword matches
        keywords = item.get("keywords", [])
        matched_kws = [kw for kw in keywords if kw.lower() in query_norm]
        score += len(matched_kws) * 20.0

        # Sequence match with full description
        desc_sim = difflib.SequenceMatcher(
            None, query_norm, normalize_string(item["description"])
        ).ratio() * 50.0
        score += desc_sim

        if score > best_score:
            best_score = score
            best_entry = item

    # Default fallback if no clear match
    if not best_entry or best_score < 15.0:
        best_entry = MOCK_HS_DATABASE[-1]  # Default telecom/network switch or generic
        confidence = 45.0
    else:
        confidence = min(98.0, round(best_score + 25.0, 1))

    response = LookupHSCodeResponse(
        query_description=description,
        matched_hs_code=best_entry["hs_code"],
        classification_description=best_entry["description"],
        dual_use_indicator=best_entry["dual_use_indicator"],
        eccn_mapping=best_entry["eccn_mapping"],
        licensing_prerequisites=best_entry["licensing_prerequisites"],
        confidence_score=confidence,
    )
    return response.model_dump()


@mcp.tool(name="verify_dual_use")
def verify_dual_use(product_spec: str) -> Dict[str, Any]:
    """
    Evaluates technical parameters (semiconductor operating frequency, cryptography key length,
    thermal imaging resolution, FPGA gate count, DSP performance) against EU Dual-Use Regulation
    (Annex I) and Wassenaar Arrangement.
    """
    spec_lower = product_spec.lower()
    findings: List[str] = []
    is_dual = False
    matched_eccn = "EAR99"
    category = "General Commercial"
    licensing_required = False

    # Check 1: Category 3 (3A001) - High frequency semiconductors / RF
    # Rule: Operating frequency >= 31.8 GHz or > 50 GHz
    freq_ghz_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ghz|gigahertz)", spec_lower)
    if freq_ghz_match:
        freq = float(freq_ghz_match.group(1))
        if freq >= 31.8:
            findings.append(f"Operating frequency {freq} GHz exceeds 31.8 GHz threshold (EU Annex I 3A001.b.2).")
            is_dual = True
            matched_eccn = "3A001.b.2"
            category = "Category 3 - Electronics"
            licensing_required = True

    # Check 2: Category 5 - Part 2 (5A002) - Information Security & Cryptography
    # Rule: Symmetric key length > 56 bits, Asymmetric > 512 bits
    sym_crypto = re.search(r"(?:aes|symmetric|encryption|key\s*length)[^\d]*(\d{2,4})\s*(?:-?\s*bit)?", spec_lower)
    if sym_crypto:
        key_len = int(sym_crypto.group(1))
        if key_len > 56:
            findings.append(f"Symmetric key length {key_len} bits exceeds 56-bit threshold (Category 5 - 5A002.a.1).")
            is_dual = True
            if matched_eccn == "EAR99":
                matched_eccn = "5A002.a.1"
                category = "Category 5 Part 2 - Information Security"
            licensing_required = True

    asym_crypto = re.search(r"(?:rsa|elliptic|ecc|asymmetric)[^\d]*(\d{3,4})\s*(?:-?\s*bit)?", spec_lower)
    if asym_crypto:
        key_len = int(asym_crypto.group(1))
        if key_len > 512:
            findings.append(f"Asymmetric key length {key_len} bits exceeds 512-bit threshold (Category 5 - 5A002.a.1).")
            is_dual = True
            if matched_eccn == "EAR99":
                matched_eccn = "5A002.a.1"
                category = "Category 5 Part 2 - Information Security"
            licensing_required = True

    # Check 3: Category 6 (6A003) - Thermal imaging / Focal Plane Arrays
    # Rule: Frame rate > 9 Hz or high pixel count
    hz_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:hz|fps|frames\s*per\s*second)", spec_lower)
    if any(k in spec_lower for k in ["thermal", "infrared", "focal plane array", "bolometer"]):
        if hz_match and float(hz_match.group(1)) > 9.0:
            findings.append(f"Infrared / thermal imaging frame rate {hz_match.group(1)} Hz exceeds 9 Hz limit (6A003.b.4).")
            is_dual = True
            matched_eccn = "6A003.b.4"
            category = "Category 6 - Sensors and Lasers"
            licensing_required = True

    # Check 4: Category 9 (9A012) - Unmanned aerial systems / military UAVs
    if any(k in spec_lower for k in ["uav", "autonomous drone", "autonomous flight", "loitering munition"]):
        findings.append("Autonomous navigation / unmanned aerial vehicle system meets Category 9 dual-use criteria (9A012).")
        is_dual = True
        matched_eccn = "9A012"
        category = "Category 9 - Aerospace and Propulsion"
        licensing_required = True

    # Check 5: Rad-hardened or military temperature ranges
    if any(k in spec_lower for k in ["radiation hardened", "rad-hard", "mil-std-883", "space qualified"]):
        findings.append("Radiation-hardened / space-qualified rating triggers Category 3 (3A001.a.1).")
        is_dual = True
        matched_eccn = "3A001.a.1"
        category = "Category 3 - Electronics"
        licensing_required = True

    if not findings:
        findings.append("No technical parameters exceeded Annex I / Wassenaar control thresholds.")
        recommendation = "Standard commercial export procedures apply. Verify destination country and end-user screening."
    else:
        recommendation = f"Item classified under {matched_eccn}. Mandatory export authorization required prior to shipment."

    response = VerifyDualUseResponse(
        product_spec=product_spec,
        is_dual_use=is_dual,
        matched_eccn=matched_eccn if is_dual else "EAR99",
        category=category,
        regulatory_framework="EU Dual-Use Regulation (Annex I) / Wassenaar Arrangement",
        licensing_required=licensing_required,
        threshold_findings=findings,
        compliance_recommendation=recommendation,
    )
    return response.model_dump()


__all__ = [
    "mcp",
    "screen_entity",
    "lookup_hs_code",
    "verify_dual_use",
    "MOCK_SANCTIONS_DB",
    "MOCK_HS_DATABASE",
    "ScreenEntityResponse",
    "LookupHSCodeResponse",
    "VerifyDualUseResponse",
    "_normalize_string",
    "_calculate_fuzzy_score",
]

if __name__ == "__main__":
    print(f"Starting {mcp.name} FastMCP server...")
    if hasattr(mcp, "run"):
        mcp.run()
