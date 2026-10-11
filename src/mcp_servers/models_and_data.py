"""Models and Mock Datasets for Compliance MCP.

Contains embedded OFAC SDN / EU Consolidated sanctions lists,
Harmonized System (HS) code mappings, and Pydantic schemas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


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
