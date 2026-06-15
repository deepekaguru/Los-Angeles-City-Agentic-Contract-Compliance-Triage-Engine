# Los-Angeles-City-Agentic-Contract-Compliance-Triage-Engine

# LA City — Agentic Contract Compliance & Triage Engine

A multi-agent procurement compliance system built for the City of Los Angeles Department of General Services. The app ingests vendor transaction line-items, runs them through a two-agent AI pipeline to validate them against contract rules, and persists structured audit verdicts to a relational database.

**Live demo:** https://los-angeles-city-agentic-contract-compliance-triage-engine-7zb.streamlit.app/

## Overview

Municipal procurement involves thousands of vendor contracts and transaction line-items that need to be checked against budget limits and approved categories. This app automates that compliance check using two coordinated AI agents:

1. **Compliance Auditor Agent** — evaluates a transaction against its linked contract (budget ceiling, approved category) and returns a status: `PASSED`, `FLAGGED`, or `CRITICAL`.
2. **Triage & Notification Agent** — takes the Auditor's verdict and generates a formal, human-readable reasoning summary for the audit log.

Both agents use OpenAI's `gpt-4o-mini` with structured JSON outputs, and both have deterministic fallback logic so the pipeline degrades gracefully if the API call fails.

## Architecture

```
Streamlit UI
   |
   v
execute_agentic_audit()
   |
   +--> read_contract_details()  (DB tool)
   |
   +--> Compliance Auditor Agent  --> status
   |
   +--> Triage & Notification Agent --> reasoning_summary
   |
   +--> write_audit_log()  (DB tool)
```

## Database Schema (SQLite)

- **contracts**: `contract_id`, `vendor_name`, `max_budget`, `approved_category`
- **transactions**: `transaction_id`, `contract_id`, `amount`, `category`, `timestamp`
- **compliance_audit_logs**: `log_id`, `transaction_id`, `status`, `reasoning_summary`

## Features

- Stage new transaction line-items via a form
- Run batch agentic audits on all pending (un-audited) transactions
- Live dashboard with metrics (total transactions, audited, pending, flagged/critical)
- Color-coded status badges (🟢 PASSED, 🟡 FLAGGED, 🔴 CRITICAL)

## Setup

### 1. Clone and install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your OpenAI API key

**Local development (.env):**

```bash
cp .env.example .env
# then edit .env and add your real key
```

**Streamlit Cloud:** add `OPENAI_API_KEY` in the app's Secrets manager.

### 3. Run the app

```bash
streamlit run app.py
```

The SQLite database (`la_city_procurement.db`) is created and seeded automatically on first run.

## Documentation

- [Business Statement](Business_statement.md)
- [Logical Structure](Logical_structure.md)
- [Technical Implementation Guide](technical_guide.md)

## Tech Stack

Python, Streamlit, SQLite, OpenAI API (`gpt-4o-mini`), pandas
