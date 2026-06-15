# Technical Implementation Guide

This guide outlines the explicit, step-by-step instructions for implementing the application components in Python 3.10+.

## Step 1: Database Initialization
* Use Python's built-in `sqlite3` library.
* Establish a database file named `la_city_procurement.db`.
* Execute DDL statements to construct the `contracts`, `transactions`, and `compliance_audit_logs` tables as defined in the Logical Structure Document.
* Seed the `contracts` table with baseline data to test boundaries (e.g., Contract 'CON-101' for vendor 'Titan Tech Solutions' with a budget of 150000.00 and category 'IT').

## Step 2: Tool Design & Database Access Layer
To enable agentic interactions with the database, expose Python functions that the agent pipeline calls directly:
* `read_contract_details(contract_id: str)`: Executes a `SELECT` statement to pull compliance constraints for the linked contract.
* `write_audit_log(transaction_id: str, status: str, reasoning_summary: str)`: Executes an `INSERT` statement into `compliance_audit_logs`.

## Step 3: Multi-Agent Orchestration Blueprint
* Use the `openai` Python SDK with the `gpt-4o-mini` model.
* Store the API key in Streamlit secrets (`st.secrets["OPENAI_API_KEY"]`); never hardcode credentials.
* Enforce structured JSON output via `response_format={"type": "json_object"}` to ensure deterministic parsing of agent responses.

### Agent 1: Compliance Auditor Agent
* Input: transaction details (`transaction_id`, `amount`, `category`) plus the linked contract record fetched via `read_contract_details`.
* Logic: compares the transaction amount against `max_budget` and the transaction category against `approved_category`.
* Output schema: `{"status": "PASSED" | "FLAGGED" | "CRITICAL"}`
* Fallback: if the API call fails, a deterministic rules check (amount/category/contract validity) assigns the status so the pipeline degrades gracefully.

### Agent 2: Triage & Notification Agent
* Input: the transaction details, contract record, and the status returned by the Auditor Agent.
* Logic: generates a formal, human-readable audit explanation for the assigned status.
* Output schema: `{"transaction_id": str, "status": str, "reasoning_summary": str}`
* Fallback: if the API call fails, a placeholder reasoning summary is written so the audit log entry is never blocked.

### Orchestration Flow
`execute_agentic_audit(txn_id, contract_id, amount, category)`:
1. Fetch contract context via `read_contract_details`.
2. Call the Auditor Agent to obtain `status`.
3. Call the Triage Agent (passing the Auditor's status) to obtain `reasoning_summary`.
4. Persist both via `write_audit_log`.

## Step 4: Frontend UI Framework
* Implement a `Streamlit` application interface.
* Create a side panel / form for seeding new transaction line items.
* Render the database tables cleanly using `st.dataframe()`.
* Add an action button ("Execute Autonomous Multi-Agent Compliance Audit") that processes all pending (un-audited) transactions through the two-agent pipeline and refreshes the application state upon completion.