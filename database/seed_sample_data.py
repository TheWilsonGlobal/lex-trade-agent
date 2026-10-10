"""Database seeder script for lex-trade-agent.

Initializes SQLite database using database/schema.sql and populates diverse
historical trade compliance precedents and audit traces.
"""

from __future__ import annotations

import os
import sqlite3
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent.memory.hybrid_memory import AgentEpisodicMemory

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

SAMPLE_EPISODES = [
    {
        "shipment_id": "HIST-2025-0101",
        "query_text": "Audit export to entity 'Nordic Logistics GmbH' (DE). Commodity: Standard commercial business laptops. Specs: Intel Core i5 processor at 2.4 GHz, standard commercial OS.",
        "action_plan": [
            "Screen recipient 'Nordic Logistics GmbH' in country 'DE'",
            "Lookup HS Code for commercial business laptops",
            "Verify dual use parameters against Category 4/5",
            "Synthesize clearance determination",
        ],
        "tool_calls": [
            {
                "name": "screen_entity",
                "arguments": {"name": "Nordic Logistics GmbH", "country": "DE"},
                "result": {"status": "CLEARED", "risk_level": "LOW", "highest_confidence": 12.0},
            },
            {
                "name": "lookup_hs_code",
                "arguments": {"description": "Standard commercial business laptops"},
                "result": {"matched_hs_code": "8471.30", "dual_use_indicator": False, "eccn_mapping": ["EAR99"]},
            },
            {
                "name": "verify_dual_use",
                "arguments": {"product_spec": "Intel Core i5 processor at 2.4 GHz"},
                "result": {"is_dual_use": False, "matched_eccn": "EAR99", "licensing_required": False},
            },
        ],
        "verdict": {
            "determination_summary": "Shipment CLEARED under NLR (No License Required). Recipient not restricted and items are standard commercial EAR99.",
            "completed_turns": 3,
        },
        "risk_level": "LOW",
    },
    {
        "shipment_id": "HIST-2025-0422",
        "query_text": "Audit export to entity 'Al-Amana Industrial Logistics FZE' (AE). Commodity: Unmanned aerial vehicle flight control systems. Specs: Autonomous GPS-denied navigation, loitering capability.",
        "action_plan": [
            "Screen recipient against EU & OFAC consolidated sanctions",
            "Lookup HS code for drone flight controller",
            "Verify Category 9 UAV technical thresholds",
            "Issue emergency transaction block",
        ],
        "tool_calls": [
            {
                "name": "screen_entity",
                "arguments": {"name": "Al-Amana Industrial Logistics FZE", "country": "AE"},
                "result": {
                    "status": "HUMAN_ESCALATION_REQUIRED",
                    "risk_level": "CRITICAL_HIGH",
                    "highest_confidence": 96.0,
                    "matched_record": {"name": "Al-Amana Industrial Logistics FZE", "list": "EU-CONSOLIDATED", "program": "EU-IRAN-SANCTIONS"},
                },
            },
            {
                "name": "lookup_hs_code",
                "arguments": {"description": "Unmanned aerial vehicle flight control systems"},
                "result": {"matched_hs_code": "8806.20", "dual_use_indicator": True, "eccn_mapping": ["9A012"]},
            },
            {
                "name": "verify_dual_use",
                "arguments": {"product_spec": "Autonomous GPS-denied navigation, loitering capability"},
                "result": {"is_dual_use": True, "matched_eccn": "9A012", "licensing_required": True},
            },
        ],
        "verdict": {
            "determination_summary": "TRANSACTION BLOCKED. Recipient listed on EU Iran sanctions for UAV procurement. Military dual-use ECCN 9A012.",
            "completed_turns": 3,
        },
        "risk_level": "CRITICAL_HIGH",
    },
    {
        "shipment_id": "HIST-2025-0819",
        "query_text": "Audit export to entity 'Pacific Micro Devices Inc' (SG). Commodity: Radiation-tolerant FPGA microchips. Specs: Total ionizing dose 100 krad(Si), military grade temperature range.",
        "action_plan": [
            "Screen recipient in Singapore",
            "Lookup semiconductor HS tariff code",
            "Verify radiation hardness against Annex I 3A001.a.1",
            "Flag dual-use permit required",
        ],
        "tool_calls": [
            {
                "name": "screen_entity",
                "arguments": {"name": "Pacific Micro Devices Inc", "country": "SG"},
                "result": {"status": "CLEARED", "risk_level": "LOW", "highest_confidence": 20.0},
            },
            {
                "name": "lookup_hs_code",
                "arguments": {"description": "Radiation-tolerant FPGA microchips"},
                "result": {"matched_hs_code": "8542.31", "dual_use_indicator": True, "eccn_mapping": ["3A001.a"]},
            },
            {
                "name": "verify_dual_use",
                "arguments": {"product_spec": "Total ionizing dose 100 krad(Si), radiation hardened"},
                "result": {"is_dual_use": True, "matched_eccn": "3A001.a.1", "licensing_required": True},
            },
        ],
        "verdict": {
            "determination_summary": "DUAL_USE_RESTRICTED. Recipient is cleared, but radiation-hardened semiconductor triggers Category 3 (3A001.a.1). Valid individual export permit required.",
            "completed_turns": 3,
        },
        "risk_level": "DUAL_USE_RESTRICTED",
    },
    {
        "shipment_id": "HIST-2025-1105",
        "query_text": "Audit export to entity 'CyberShield Telemetry Ltd' (GB). Commodity: Secure cryptographic gateway router. Specs: Hardware accelerated AES-256 encryption engine with RSA-4096 key exchange.",
        "action_plan": [
            "Screen UK entity",
            "Classify networking and cryptographic hardware",
            "Evaluate Category 5 Part 2 cryptography thresholds",
            "Flag export authorization requirements",
        ],
        "tool_calls": [
            {
                "name": "screen_entity",
                "arguments": {"name": "CyberShield Telemetry Ltd", "country": "GB"},
                "result": {"status": "CLEARED", "risk_level": "LOW", "highest_confidence": 18.0},
            },
            {
                "name": "lookup_hs_code",
                "arguments": {"description": "Secure cryptographic gateway router"},
                "result": {"matched_hs_code": "8517.62", "dual_use_indicator": True, "eccn_mapping": ["5A002"]},
            },
            {
                "name": "verify_dual_use",
                "arguments": {"product_spec": "AES-256 encryption engine with RSA-4096 key exchange"},
                "result": {"is_dual_use": True, "matched_eccn": "5A002.a.1", "licensing_required": True},
            },
        ],
        "verdict": {
            "determination_summary": "DUAL_USE_RESTRICTED. Symmetric key > 56 bits and asymmetric key > 512 bits trigger 5A002.a.1 information security controls.",
            "completed_turns": 3,
        },
        "risk_level": "DUAL_USE_RESTRICTED",
    },
]


def init_schema(db_path: str) -> None:
    """Execute schema.sql against SQLite database."""
    if os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            sql_script = f.read()
        with sqlite3.connect(db_path) as conn:
            conn.executescript(sql_script)
            conn.commit()


def seed_database(db_path: str = "lex_trade_memory.db") -> None:
    """Populate database with sample episodes and audit trails."""
    print(f"[*] Initializing schema and seeding data into: {db_path}")
    init_schema(db_path)
    memory = AgentEpisodicMemory(db_path=db_path)

    for ep in SAMPLE_EPISODES:
        ep_id = memory.record_episode(
            shipment_id=ep["shipment_id"],
            query_text=ep["query_text"],
            action_plan=ep["action_plan"],
            tool_calls=ep["tool_calls"],
            verdict=ep["verdict"],
            risk_level=ep["risk_level"],
        )

        for tc in ep["tool_calls"]:
            memory.record_audit_step(
                shipment_id=ep["shipment_id"],
                step_name=f"tool_{tc['name']}",
                payload=tc,
            )

        print(f"  -> Inserted Episode #{ep_id}: [{ep['shipment_id']}] {ep['risk_level']}")

    print("\n[+] Database seeding complete! Precedent episodes ready for semantic retrieval.")


if __name__ == "__main__":
    target_db = os.path.join(PROJECT_ROOT, "lex_trade_memory.db")
    seed_database(target_db)
