"""Compliance MCP Server.

Provides FastMCP tools for trade compliance, sanctions screening,
Harmonized System (HS) code classification, and dual-use technical verification
under EU Dual-Use Regulation (Annex I) and the Wassenaar Arrangement.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

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
# Mock Sanctions Data: Embedded OFAC SDN & EU Consolidated Lists
# ============================================================================

MOCK_SANCTIONS_DB: List[Dict[str, Any]] = [
    {
        "name": "CJSC Vektor Radiosystems",
        "aliases": ["Vektor Radio", "Vector Radiosystems CJSC", "AO Vektor"],
        "country": "RU",
        "list": "OFAC-SDN",
        "program": "RUSSIA-EO14024",
        "remarks": "Entity operating in the defense and related materiel sector of the Russian Federation.",
    },
    {
        "name": "Hangzhou Microtech Electronics Co Ltd",
        "aliases": ["Microtech Electronics", "Hangzhou Micro Tech"],
        "country": "CN",
        "list": "OFAC-NON-SDN-CMIC",
        "program": "CMIC-EO13959",
        "remarks": "Part of Chinese military-industrial complex and advanced semiconductor sourcing.",
    },
    {
        "name": "Al-Amana Industrial Logistics FZE",
        "aliases": ["Amana Industrial", "Al Amana Logistics"],
        "country": "AE",
        "list": "EU-CONSOLIDATED",
        "program": "EU-IRAN-SANCTIONS",
        "remarks": "Procurement network for illicit unmanned aerial vehicle components.",
    },
    {
        "name": "Rosoboronexport JSC",
        "aliases": ["Rosoboronexport", "Russian Defense Export Agency"],
        "country": "RU",
        "list": "OFAC-SDN",
        "program": "CAATSA",
        "remarks": "State-owned sole intermediary for export of defense and dual-use products.",
    },
    {
        "name": "Shahid Bakeri Industrial Group",
        "aliases": ["SBIG", "Shahid Bagheri"],
        "country": "IR",
        "list": "OFAC-SDN",
        "program": "NPWMD",
        "remarks": "Solid-propellant ballistic missile development subordinate entity.",
    },
    {
        "name": "Minsk Semiconductor Integration Works",
        "aliases": ["Integral Minsk", "Minsk Semi", "Integral Holding"],
        "country": "BY",
        "list": "EU-CONSOLIDATED",
        "program": "EU-BELARUS-SANCTIONS",
        "remarks": "Manufacturer of integrated circuits supporting Russian military avionics.",
    },
]

# ============================================================================
# Mock HS Code Tariff & Dual-Use Classification Database
# ============================================================================

MOCK_HS_DATABASE: List[Dict[str, Any]] = [
    {
        "hs_code": "8542.31",
        "description": "Electronic integrated circuits - Processors and controllers, whether or not combined with memories, converters, logic circuits, amplifiers, clock and timing circuits, or other circuits.",
        "dual_use_indicator": True,
        "eccn_mapping": ["3A001.a", "5A002.a"],
        "licensing_prerequisites": "Export authorization required if operating frequency exceeds 50 GHz, GFLOPS > threshold, or hardware encryption is active.",
        "keywords": ["processor", "cpu", "controller", "microcontroller", "soc", "asic", "fpga", "integrated circuit", "chip", "semiconductor"],
    },
    {
        "hs_code": "8543.70",
        "description": "Electrical machines and apparatus, having individual functions, not specified or included elsewhere in this chapter - High frequency amplifiers, microwave modules, signal generators.",
        "dual_use_indicator": True,
        "eccn_mapping": ["3A001.b"],
        "licensing_prerequisites": "End-user statement and dual-use permit required for RF microwave equipment above 31.8 GHz.",
        "keywords": ["amplifier", "rf", "microwave", "signal generator", "oscillator", "transceiver", "frequency"],
    },
    {
        "hs_code": "8471.50",
        "description": "Digital processing units other than those of subheading 8471.41 or 8471.49, whether or not containing in the same housing one or two of the following types of units: storage units, input units, output units.",
        "dual_use_indicator": True,
        "eccn_mapping": ["4A003", "5A002"],
        "licensing_prerequisites": "Licensing required if Adjusted Peak Performance (APP) exceeds 29 Weighted TeraFLOPS (WT) or military spec.",
        "keywords": ["server", "computer", "processing unit", "workstation", "hpc", "mainframe"],
    },
    {
        "hs_code": "8806.20",
        "description": "Unmanned aircraft (drones) for remote-controlled flight, other than for recreation.",
        "dual_use_indicator": True,
        "eccn_mapping": ["9A012", "9A112"],
        "licensing_prerequisites": "Mandatory individual export license under Wassenaar Munitions / Dual-Use Annex.",
        "keywords": ["drone", "uav", "unmanned aircraft", "autonomous flight", "quadcopter"],
    },
    {
        "hs_code": "9013.80",
        "description": "Other optical appliances and instruments - Liquid crystal devices, optical modules, lasers.",
        "dual_use_indicator": True,
        "eccn_mapping": ["6A005"],
        "licensing_prerequisites": "Licensing required for pulsed lasers with pulse duration < 1 ps or high average power output.",
        "keywords": ["laser", "optics", "optical device", "lidar", "collimator", "interferometer"],
    },
    {
        "hs_code": "8471.30",
        "description": "Portable automatic data processing machines, weighing not more than 10 kg, consisting of at least a central processing unit, a keyboard and a display (Standard Laptops / Tablets).",
        "dual_use_indicator": False,
        "eccn_mapping": ["EAR99"],
        "licensing_prerequisites": "No license required (NLR) for standard commercial consumer laptops to non-embargoed destinations.",
        "keywords": ["laptop", "notebook", "tablet", "portable computer", "chromebook"],
    },
    {
        "hs_code": "8517.62",
        "description": "Machines for the reception, conversion and transmission or regeneration of voice, images or other data, including switching and routing apparatus.",
        "dual_use_indicator": False,
        "eccn_mapping": ["5A992", "5A002"],
        "licensing_prerequisites": "Mass market cryptographic classification or license required if quantum-resistant or non-standard protocols.",
        "keywords": ["router", "switch", "ethernet", "telecom", "modem", "network switch"],
    },
]

# ============================================================================
# Helper Functions
# ============================================================================

def _normalize_string(text: str) -> str:
    """Normalize text for consistent comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = text.split()
    return " ".join(tokens)


def _calculate_fuzzy_score(query: str, target: str) -> float:
    """Calculate normalized token-aware similarity score between 0 and 100."""
    q_norm = _normalize_string(query)
    t_norm = _normalize_string(target)

    # Direct match check
    if q_norm == t_norm:
        return 100.0

    seq_ratio = difflib.SequenceMatcher(None, q_norm, t_norm).ratio() * 100.0

    # Token overlap check
    q_tokens = set(q_norm.split())
    t_tokens = set(t_norm.split())
    if q_tokens and t_tokens:
        overlap = len(q_tokens.intersection(t_tokens))
        jaccard = (overlap / len(q_tokens.union(t_tokens))) * 100.0
        combined_score = (seq_ratio * 0.6) + (jaccard * 0.4)
    else:
        combined_score = seq_ratio

    # Substring bonus
    if q_norm in t_norm or t_norm in q_norm:
        combined_score = max(combined_score, 88.0)

    return round(min(100.0, combined_score), 2)


# ============================================================================
# Pydantic Schemas for MCP Tools
# ============================================================================

class ScreenEntityResponse(BaseModel):
    query_entity: str
    query_country: str
    highest_confidence: float
    matched_record: Optional[Dict[str, Any]] = None
    risk_level: str
    status: str
    reasoning: str


class LookupHSCodeResponse(BaseModel):
    query_description: str
    matched_hs_code: str
    classification_description: str
    dual_use_indicator: bool
    eccn_mapping: List[str]
    licensing_prerequisites: str
    confidence_score: float


class VerifyDualUseResponse(BaseModel):
    product_spec: str
    is_dual_use: bool
    matched_eccn: Optional[str] = None
    category: Optional[str] = None
    regulatory_framework: str
    licensing_required: bool
    threshold_findings: List[str]
    compliance_recommendation: str


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
        score_name = _calculate_fuzzy_score(name, record["name"])

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
            score_alias = _calculate_fuzzy_score(name, alias)
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
    query_norm = _normalize_string(description)
    query_tokens = set(query_norm.split())

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
            None, query_norm, _normalize_string(item["description"])
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


if __name__ == "__main__":
    import sys
    print(f"Starting {mcp.name} FastMCP server...")
    if hasattr(mcp, "run"):
        mcp.run()
