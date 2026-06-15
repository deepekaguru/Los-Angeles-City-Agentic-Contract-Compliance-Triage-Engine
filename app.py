import streamlit as st
import sqlite3

import json
import os
import pandas as pd
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# -----------------------------------------------------------------------------
# 1. DATABASE MANAGEMENT & SEEDING
# -----------------------------------------------------------------------------
DB_FILE = "la_city_procurement.db"


def init_db():
    """Initializes the database and seeds it with mock municipal data."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create tables
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contracts (
        contract_id TEXT PRIMARY KEY,
        vendor_name TEXT NOT NULL,
        max_budget REAL NOT NULL,
        approved_category TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id TEXT PRIMARY KEY,
        contract_id TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY(contract_id) REFERENCES contracts(contract_id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compliance_audit_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT NOT NULL,
        status TEXT NOT NULL,
        reasoning_summary TEXT NOT NULL,
        FOREIGN KEY(transaction_id) REFERENCES transactions(transaction_id)
    )""")

    # Seed mock contract data if empty
    cursor.execute("SELECT COUNT(*) FROM contracts")
    if cursor.fetchone()[0] == 0:
        contracts_data = [
            ("CON-101", "Titan Tech Solutions", 150000.00, "IT"),
            ("CON-202", "Greenery Landscaping LLC", 45000.00, "Logistics"),
            ("CON-303", "Apex Office Supplies", 15000.00, "Administrative")
        ]
        cursor.executemany("INSERT INTO contracts VALUES (?, ?, ?, ?)", contracts_data)

        # Seed initial pending transactions
        transactions_data = [
            ("TXN-001", "CON-101", 12000.00, "IT", "2026-06-10 10:00:00"),
            ("TXN-002", "CON-101", 165000.00, "IT", "2026-06-11 11:30:00"),  # Budget Exceeded
            ("TXN-003", "CON-202", 3500.00, "Catering", "2026-06-12 14:15:00")  # Wrong Category
        ]
        cursor.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", transactions_data)

    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# 2. CORE UTILITIES
# -----------------------------------------------------------------------------
def read_contract_details(contract_id: str) -> str:
    """Fetches full compliance constraints for a given contract ID."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return f"Contract ID: {row[0]} | Vendor: {row[1]} | Max Allowed Budget: ${row[2]} | Permitted Category: {row[3]}"
    return f"Error: Contract {contract_id} not found in database registry."


def write_audit_log(transaction_id: str, status: str, reasoning_summary: str) -> str:
    """Inserts an automated audit verdict back into the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO compliance_audit_logs (transaction_id, status, reasoning_summary) VALUES (?, ?, ?)",
        (transaction_id, status, reasoning_summary)
    )
    conn.commit()
    conn.close()
    return "Audit outcome successfully committed to database."


# -----------------------------------------------------------------------------
# 3. COMPLIANCE AGENT CORE (AGENTIC EVALUATION VIA OPENAI)
# -----------------------------------------------------------------------------
def run_auditor_agent(txn_id, contract_context, amount, category) -> dict:
    """
    Compliance Auditor Agent: evaluates a transaction against its contract
    record and returns a structured verdict {"status": "PASSED"|"FLAGGED"|"CRITICAL"}.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    prompt = (
        f"You are the Compliance Auditor Agent for a municipal procurement system. "
        f"Evaluate transaction {txn_id} for ${amount:,.2f} in category '{category}' "
        f"against this contract record: {contract_context}. "
        f"Rules: if the amount exceeds the contract's max budget, or the contract "
        f"is missing/invalid, the status is 'CRITICAL'. If the category does not "
        f"match the contract's approved category, the status is 'FLAGGED'. "
        f"Otherwise the status is 'PASSED'. "
        f"Respond with ONLY a JSON object: {{\"status\": \"PASSED\"|\"FLAGGED\"|\"CRITICAL\"}}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        status = result.get("status", "FLAGGED")
        if status not in ("PASSED", "FLAGGED", "CRITICAL"):
            status = "FLAGGED"
        return {"status": status}
    except Exception:
        # Deterministic fallback if the Auditor Agent call fails
        if amount > 150000.00 or "Error" in contract_context:
            return {"status": "CRITICAL"}
        elif category not in contract_context:
            return {"status": "FLAGGED"}
        return {"status": "PASSED"}


def run_triage_agent(txn_id, status, contract_context, amount, category) -> str:
    """
    Triage & Notification Agent: takes the Auditor Agent's verdict and
    generates a natural-language reasoning summary for the audit log.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    prompt = (
        f"You are the Triage & Notification Agent for a municipal procurement system. "
        f"The Compliance Auditor Agent evaluated transaction {txn_id} "
        f"(${amount:,.2f}, category '{category}', contract record: {contract_context}) "
        f"and assigned status '{status}'. "
        f"Write a one to two sentence reasoning summary in formal audit language "
        f"explaining this verdict, suitable for a compliance log. "
        f"Respond with ONLY a JSON object: {{\"transaction_id\": \"{txn_id}\", "
        f"\"status\": \"{status}\", \"reasoning_summary\": \"...\"}}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("reasoning_summary", f"Status: {status}.")
    except Exception as e:
        return f"[Triage Agent unavailable, fallback] Status: {status}. ({e})"


def execute_agentic_audit(txn_id, contract_id, amount, category):
    """
    Agentic municipal compliance verification loop.
    Orchestrates two agents:
      1. Compliance Auditor Agent -> determines status (PASSED/FLAGGED/CRITICAL)
      2. Triage & Notification Agent -> generates the reasoning summary
    """
    # Fetch real-time truth from database using tool logic
    contract_context = read_contract_details(contract_id)

    # Agent 1: Compliance Auditor Agent determines the verdict
    audit_result = run_auditor_agent(txn_id, contract_context, amount, category)
    status = audit_result["status"]

    # Agent 2: Triage & Notification Agent generates the reasoning summary
    reasoning_summary = run_triage_agent(txn_id, status, contract_context, amount, category)

    # Execute write tool back to relational tables
    write_audit_log(txn_id, status, reasoning_summary)


# -----------------------------------------------------------------------------
# 4. FRONTEND STREAMLIT UI RUNTIME
# -----------------------------------------------------------------------------
def status_badge(status: str) -> str:
    """Returns a colored emoji badge for a given audit status."""
    return {"PASSED": "🟢 PASSED", "FLAGGED": "🟡 FLAGGED", "CRITICAL": "🔴 CRITICAL"}.get(status, status)


def run_ui():
    st.set_page_config(page_title="Los Angeles City Agentic Compliance Engine", layout="wide", page_icon="📋")

    st.markdown("<h4 style='text-align: center;'>Los Angeles City — Agentic Contract Compliance & Triage Engine</h4>",
                unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Department of General Services · Multi-Agent Procurement Compliance System</p>",
        unsafe_allow_html=True)
    st.divider()

    init_db()
    conn = sqlite3.connect(DB_FILE)

    # ---- Top-level metrics ----
    total_txns = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    audited = conn.execute("SELECT COUNT(*) FROM compliance_audit_logs").fetchone()[0]
    pending = total_txns - audited
    flagged_critical = conn.execute(
        "SELECT COUNT(*) FROM compliance_audit_logs WHERE status IN ('FLAGGED', 'CRITICAL')"
    ).fetchone()[0]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Transactions", total_txns)
    m2.metric("Audited", audited)
    m3.metric("Pending Audit", pending)
    m4.metric("Flagged / Critical", flagged_critical)

    st.divider()

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("**Active Procurement Rules**")
        contracts_df = pd.read_sql_query("SELECT * FROM contracts", conn)
        contracts_df.columns = ["Contract ID", "Vendor Entity", "Allocated Budget ($)", "Category Scope"]
        st.dataframe(contracts_df, hide_index=True, use_container_width=True)

        st.markdown("**Stage New Invoice Payload**")
        with st.form("new_txn_form"):
            new_id = st.text_input("Transaction ID", value=f"TXN-{int(datetime.now().timestamp()) % 10000}")
            contract_choice = st.selectbox("Associate Contract", ["CON-101", "CON-202", "CON-303", "CON-999"])
            input_amount = st.number_input("Invoice Amount ($)", min_value=0.0, value=2500.0)
            input_cat = st.text_input("Service Line Item Category", value="IT")

            if st.form_submit_button("Inject Transaction Line Item", use_container_width=True):
                conn.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
                             (new_id, contract_choice, input_amount, input_cat,
                              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                st.success(f"Transaction {new_id} added to the queue")
                st.rerun()

    with col2:
        st.markdown("**1. Ingested Transaction Logs Queue**")
        txns_df = pd.read_sql_query("SELECT * FROM transactions", conn)
        txns_df.columns = ["Txn ID", "Contract Linked", "Amount ($)", "Category Code", "Timestamp Ingested"]
        st.dataframe(txns_df, hide_index=True, use_container_width=True)

        if st.button("🚀 Execute Autonomous Multi-Agent Compliance Audit", type="primary", use_container_width=True):
            unaudited = conn.execute("""
                SELECT t.transaction_id, t.contract_id, t.amount, t.category 
                FROM transactions t
                LEFT JOIN compliance_audit_logs l ON t.transaction_id = l.transaction_id
                WHERE l.log_id IS NULL
            """).fetchall()

            if not unaudited:
                st.info("All transactions are audited. No pending validation items found.")
            else:
                with st.spinner("Orchestrating Auditor & Triage Agents..."):
                    for txn in unaudited:
                        execute_agentic_audit(txn[0], txn[1], txn[2], txn[3])
                st.success("Agent batch processing complete")
                st.rerun()

        st.markdown("**2. Evaluated Compliance Auditing Matrix**")
        logs_df = pd.read_sql_query("""
            SELECT l.log_id, l.transaction_id, t.contract_id, l.status, l.reasoning_summary 
            FROM compliance_audit_logs l
            JOIN transactions t ON l.transaction_id = t.transaction_id
            ORDER BY l.log_id DESC
        """, conn)

        if not logs_df.empty:
            logs_df["status"] = logs_df["status"].apply(status_badge)
        logs_df.columns = ["Log ID", "Txn ID", "Contract Ref", "Agent Verdict", "Audit Reasoning"]
        st.dataframe(logs_df, hide_index=True, use_container_width=True)

    conn.close()


if __name__ == "__main__":
    run_ui()