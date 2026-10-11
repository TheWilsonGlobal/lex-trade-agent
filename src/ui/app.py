"""LexTrade Agent - Autonomous Trade Compliance & Export Control Cockpit.

Streamlit enterprise UI providing:
1. Live compliance audit runner with interactive ReAct reasoning loop visualization.
2. FastMCP tool invocation cards (screen_entity, lookup_hs_code, verify_dual_use).
3. Hybrid episodic memory & SQLite precedent explorer with cosine vector search.
4. Non-repudiation audit trail viewer.
5. On-demand 4-Pillar Non-Lexical Agent Benchmark dashboard.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from typing import Any, Dict, List

from dotenv import load_dotenv
import streamlit as st

# Configure project path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (PROJECT_ROOT, SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

# Load environment variables from .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

import importlib
import agent.hermes_orchestrator
importlib.reload(agent.hermes_orchestrator)

from agent.hermes_orchestrator import HermesAgent, create_llm_client
from agent.memory.hybrid_memory import AgentEpisodicMemory
from database.seed_sample_data import seed_database
from eval.agent_eval import ComplianceEvaluationBenchmark

# Page Configuration
st.set_page_config(
    page_title="LexTrade Compliance Cockpit",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .status-badge {
        display: inline-block;
        padding: 0.35rem 0.8rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        margin-right: 0.5rem;
    }
    .badge-critical { background-color: #FEE2E2; color: #991B1B; border: 1px solid #F87171; }
    .badge-dual { background-color: #FEF3C7; color: #92400E; border: 1px solid #FCD34D; }
    .badge-cleared { background-color: #D1FAE5; color: #065F46; border: 1px solid #34D399; }
    .tool-box {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.8rem;
    }
    .scratchpad-box {
        background-color: #F1F5F9;
        border-left: 4px solid #6366F1;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.9rem;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

DB_PATH = os.path.join(PROJECT_ROOT, "lex_trade_memory.db")


# Helper to get memory instance
@st.cache_resource
def get_memory() -> AgentEpisodicMemory:
    return AgentEpisodicMemory(db_path=DB_PATH)


memory = get_memory()

# ============================================================================
# Sidebar: System Status & Demo Presets
# ============================================================================

st.sidebar.image("https://img.shields.io/badge/Architecture-Hermes%20ReAct%20%2B%20FastMCP-blue?style=for-the-badge", width="stretch")
st.sidebar.title("System Controls")

llm_url = os.getenv("LLM_API_URL") or os.getenv("OPENAI_BASE_URL") or "http://localhost:8000/v1"
st.sidebar.markdown(f"**LLM Endpoint**: `{llm_url}`")
st.sidebar.markdown(f"**Database**: `lex_trade_memory.db`")

st.sidebar.markdown("---")
st.sidebar.subheader("📋 1-Click Manifest Presets")

PRESETS = {
    "🚨 Sanctioned Entity (Vektor RU)": {
        "shipment_id": "EXP-2026-8941",
        "recipient": "Vector Radiosystems",
        "country": "RU",
        "description": "High frequency gallium nitride RF power amplifier modules for microwave links",
        "spec": "Solid state GaN power amplifier module, operating frequency 34.5 GHz, integrated AES-256 telemetry",
    },
    "⚡ Chinese CMIC Semiconductor": {
        "shipment_id": "EXP-2026-9022",
        "recipient": "Hangzhou Microtech Electronics Co Ltd",
        "country": "CN",
        "description": "Multicore microprocessor integrated circuits for signal processing",
        "spec": "Operating frequency 55 GHz, high-density FPGA coprocessor",
    },
    "🛡️ Cryptographic Gateway": {
        "shipment_id": "EXP-2026-7714",
        "recipient": "CyberShield Telemetry Ltd",
        "country": "GB",
        "description": "Secure cryptographic gateway router",
        "spec": "Hardware accelerated AES-256 encryption engine with RSA-4096 key exchange",
    },
    "✅ Commercial Laptops (Cleared)": {
        "shipment_id": "EXP-2026-1045",
        "recipient": "Nordic Logistics GmbH",
        "country": "DE",
        "description": "Standard commercial business laptops with integrated webcams",
        "spec": "Standard x86 processor at 2.4 GHz, commercial OS with standard SSL/TLS",
    },
}

selected_preset = st.sidebar.selectbox("Choose a scenario:", list(PRESETS.keys()))

if st.sidebar.button("Load Selected Preset", width="stretch"):
    preset_data = PRESETS[selected_preset]
    st.session_state["shipment_id"] = preset_data["shipment_id"]
    st.session_state["recipient"] = preset_data["recipient"]
    st.session_state["country"] = preset_data["country"]
    st.session_state["description"] = preset_data["description"]
    st.session_state["spec"] = preset_data["spec"]
    st.sidebar.success(f"Loaded: {selected_preset}")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Re-Seed Historical Precedents", width="stretch"):
    with st.spinner("Seeding database..."):
        seed_database(DB_PATH)
        st.cache_resource.clear()
        st.sidebar.success("Database seeded with sample precedents!")

# ============================================================================
# Main Header
# ============================================================================

st.markdown('<div class="main-header">⚖️ LexTrade Compliance Cockpit</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Autonomous Export Control, Sanctions Screening, & Dual-Use Audit Engine powered by Hermes ReAct and FastMCP</div>',
    unsafe_allow_html=True,
)

# Tabs
tab_audit, tab_memory, tab_logs, tab_bench = st.tabs([
    "🚀 Live Compliance Audit",
    "📚 Episodic Precedents Explorer",
    "🔍 Telemetry & Audit Logs",
    "📊 4-Pillar Non-Lexical Benchmark",
])

# ============================================================================
# Tab 1: Live Compliance Audit
# ============================================================================

with tab_audit:
    st.subheader("1. Shipment Manifest Declaration")

    col1, col2 = st.columns([2, 1])
    with col1:
        shipment_id = st.text_input(
            "Shipment Tracking ID",
            value=st.session_state.get("shipment_id", "EXP-2026-8941"),
        )
        recipient = st.text_input(
            "Recipient Entity / Consignee",
            value=st.session_state.get("recipient", "Vector Radiosystems"),
        )
    with col2:
        country = st.text_input(
            "Destination Country (ISO 2-letter)",
            value=st.session_state.get("country", "RU"),
        )

    product_desc = st.text_area(
        "Commercial Commodity Description",
        value=st.session_state.get("description", "High frequency gallium nitride RF power amplifier modules for microwave links"),
        height=70,
    )

    product_spec = st.text_area(
        "Declared Technical Specifications & Operating Parameters",
        value=st.session_state.get("spec", "Solid state GaN power amplifier module, operating frequency 34.5 GHz, integrated AES-256 telemetry"),
        height=70,
    )

    run_audit = st.button("🚀 Run Autonomous Compliance Audit", type="primary", width="stretch")

    if run_audit:
        st.markdown("---")
        st.subheader("2. Hermes Autonomous Reasoning & FastMCP Execution")

        with st.spinner("Initializing Hermes Agent & searching historical memory..."):
            agent = HermesAgent(memory=memory)

            # Query memory first for UI display
            query_text = f"Audit export to entity '{recipient}' ({country}). Commodity: {product_desc}. Specs: {product_spec}."
            precedents = memory.search_episodes(query_text, top_k=2)

            if precedents:
                st.info(
                    f"🧠 **Relevant Precedent Identified in Hybrid Memory**:\n\n"
                    f"- Historical Shipment: `{precedents[0]['shipment_id']}` (Risk: **{precedents[0]['risk_level']}**)\n"
                    f"- Cosine Semantic Similarity: `{precedents[0]['similarity'] * 100:.1f}%`"
                )

            # Execute full audit
            progress_bar = st.progress(0.2)
            audit_result = agent.run_compliance_audit(
                shipment_id=shipment_id,
                recipient_entity=recipient,
                destination_country=country,
                product_description=product_desc,
                product_spec=product_spec,
            )
            progress_bar.progress(1.0)

        # Display Turn Trajectory
        st.markdown("### 📋 Trajectory & Tool Execution Details")

        tool_calls = audit_result.get("tool_calls", [])
        for i, tc in enumerate(tool_calls, start=1):
            t_name = tc.get("name")
            t_args = tc.get("arguments", {})
            t_res = tc.get("result", {})

            with st.expander(f"Turn {i}: FastMCP Tool [{t_name}]", expanded=True):
                st.markdown(f"**Arguments:** `{json.dumps(t_args)}`")

                if t_name == "screen_entity":
                    score = t_res.get("highest_confidence", 0.0)
                    status = t_res.get("status", "")
                    matched = t_res.get("matched_record")
                    st.write(f"Confidence Score: **{score}%** | Status: `{status}`")
                    if matched:
                        st.warning(f"Matched Sanction List: **{matched.get('list')}** ({matched.get('program')})")
                    st.write(f"Reasoning: {t_res.get('reasoning')}")

                elif t_name == "lookup_hs_code":
                    hs_code = t_res.get("matched_hs_code")
                    is_dual = t_res.get("dual_use_indicator")
                    eccn = t_res.get("eccn_mapping", [])
                    st.write(f"Resolved HS Code: **{hs_code}** | Dual-Use Indicator: **{is_dual}**")
                    st.write(f"ECCN Mapping: `{eccn}`")
                    st.write(f"Licensing Prerequisites: {t_res.get('licensing_prerequisites')}")

                elif t_name == "verify_dual_use":
                    is_dual = t_res.get("is_dual_use")
                    eccn = t_res.get("matched_eccn")
                    findings = t_res.get("threshold_findings", [])
                    st.write(f"Dual-Use Controlled: **{is_dual}** | ECCN: **{eccn}**")
                    st.markdown("**Threshold Findings:**")
                    for f in findings:
                        st.markdown(f"- {f}")
                    st.info(f"Recommendation: {t_res.get('compliance_recommendation')}")

        # Final Audit Verdict
        st.markdown("---")
        st.subheader("3. Final Compliance Audit Determination")

        final_risk = audit_result.get("risk_level", "LOW")
        verdict = audit_result.get("verdict", {})
        summary_text = verdict.get("determination_summary", "")

        if final_risk == "CRITICAL_HIGH":
            st.error(f"🚨 **DETERMINATION: CRITICAL_HIGH RISK — TRANSACTION BLOCKED**")
            st.markdown(
                '<span class="status-badge badge-critical">HUMAN_ESCALATION_REQUIRED</span>'
                '<span class="status-badge badge-critical">OFAC / EU EMBARGO</span>',
                unsafe_allow_html=True,
            )
        elif final_risk == "DUAL_USE_RESTRICTED":
            st.warning(f"⚠️ **DETERMINATION: DUAL_USE_RESTRICTED — EXPORT PERMIT MANDATORY**")
            st.markdown(
                '<span class="status-badge badge-dual">MANDATORY DUAL-USE LICENSE</span>'
                '<span class="status-badge badge-dual">EU ANNEX I / WASSENAAR</span>',
                unsafe_allow_html=True,
            )
        else:
            st.success(f"✅ **DETERMINATION: CLEARED / LOW RISK — NO LICENSE REQUIRED (NLR)**")
            st.markdown(
                '<span class="status-badge badge-cleared">COMMERCIAL EXPORT CLEARED</span>'
                '<span class="status-badge badge-cleared">EAR99 DE-MINIMIS</span>',
                unsafe_allow_html=True,
            )

        st.markdown(f"**Execution Metrics**: {audit_result.get('turns')} turns completed | {audit_result.get('tool_calls_executed')} tool calls executed | Episode ID #{audit_result.get('episode_id')} stored in SQLite.")
        st.markdown(summary_text)


# ============================================================================
# Tab 2: Episodic Precedents Explorer
# ============================================================================

with tab_memory:
    st.subheader("📚 SQLite Episodic Memory & Semantic Precedents")
    st.markdown("Search past compliance determinations stored in `lex_trade_memory.db` using TF-IDF / trigram cosine vector similarity.")

    search_query = st.text_input("Enter semantic query or commodity to search past episodes:", value="GaN RF microwave amplifier Russia")

    if st.button("🔍 Search Precedents", key="search_mem_btn"):
        results = memory.search_episodes(search_query, top_k=5)
        if not results:
            st.info("No matching historical episodes found.")
        else:
            st.write(f"Found **{len(results)}** semantically relevant episodes:")
            for r in results:
                score_pct = r.get("similarity", 0.0) * 100
                st.markdown(f"**Shipment `{r.get('shipment_id')}`** | Risk: **{r.get('risk_level')}** | Similarity: **{score_pct:.1f}%**")
                st.markdown(f"- Query: {r.get('query_text')}")
                st.markdown("---")

    st.markdown("### 🗄️ Raw Stored Episodes Table")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id, shipment_id, risk_level, query_text, datetime(created_at, 'unixepoch') as created_at FROM episodes ORDER BY id DESC LIMIT 50")
            ep_rows = cursor.fetchall()
            if ep_rows:
                st.dataframe([dict(r) for r in ep_rows], width="stretch")
            else:
                st.info("No episodes in database. Click 'Re-Seed Historical Precedents' in the sidebar.")
    except Exception as e:
        st.error(f"Error accessing SQLite database: {e}")


# ============================================================================
# Tab 3: Telemetry & Audit Logs
# ============================================================================

with tab_logs:
    st.subheader("🔍 Immutable Telemetry & Non-Repudiation Audit Logs")
    st.markdown("Every tool invocation, argument, response payload, and timestamp is immutably recorded in the SQLite `audit_logs` table.")

    target_shipment = st.text_input("Filter by Shipment ID:", value="EXP-2026-8941")

    if st.button("Fetch Audit Trail", key="fetch_audit_btn"):
        logs = memory.get_audit_trail(target_shipment)
        if not logs:
            st.info(f"No audit logs found for shipment ID '{target_shipment}'.")
        else:
            st.write(f"Found **{len(logs)}** audit events for `{target_shipment}`:")
            for entry in logs:
                t_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry['timestamp']))
                st.markdown(f"**[{t_str}] Step: `{entry['step_name']}`**")
                st.json(entry["payload"])
                st.markdown("---")


# ============================================================================
# Tab 4: 4-Pillar Non-Lexical Benchmark
# ============================================================================

with tab_bench:
    st.subheader("📊 4-Pillar Non-Lexical Agent Evaluation Benchmark")
    st.markdown("Run the automated non-lexical evaluation suite against multi-scenario export control test vectors:")

    if st.button("▶️ Execute 4-Pillar Benchmark Live", type="primary", key="run_benchmark_btn"):
        with st.spinner("Executing non-lexical evaluation benchmark across all test scenarios..."):
            evaluator = ComplianceEvaluationBenchmark()
            bench_results = evaluator.run_benchmark()

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Task Precision", f"{bench_results['task_completion_precision']}%", delta="Pillar 1 (40%)")
        col_m2.metric("Tool Accuracy", f"{bench_results['tool_invocation_accuracy']}%", delta="Pillar 2 (30%)")
        col_m3.metric("Token Efficiency", f"{bench_results['token_efficiency_score']}%", delta="Pillar 3 (15%)")
        col_m4.metric("Avg Latency", f"{bench_results['average_latency_ms']} ms", delta="Pillar 4 (15%)")

        st.success(f"🏆 **Composite Production Readiness Score: {bench_results['composite_score']} / 100.0**")

        st.markdown("### Evaluated Scenarios:")
        st.dataframe(bench_results.get("scenarios_evaluated", []), width="stretch")
