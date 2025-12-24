# PRT software accounting Constitution

## Core Principles

- All work must start from a written **spec** that is consistent with `.docs/tdd/PRT_TDD_v2.md`.
- No implementation PR may be opened without:
  - `specs/<feature>/spec.md`
  - `specs/<feature>/plan.md`
  - `specs/<feature>/tasks.md`
- When spec and code disagree, **spec wins** until the spec is amended.

### II. Case-Centric Accounting Model (NON-NEGOTIABLE)
- **1 Case = 1 Category = 1 Account Code = 1 CR = 1 DB**.
- If a requester needs multiple categories (e.g., books + travel), they must create **multiple cases**.
- The system must enforce constraints so that a single case cannot produce multiple CRs or DBs.

### III. Category Governance (Fixed Category + Auto-Map Account Code)
- End users must never select or view account codes.
- **Accounting/Admin only** may:
  - create categories
  - update category details
  - deactivate/reactivate categories
  - change category-to-account-code mapping
- Rules:
  - **1 Category → 1 Account Code always**
  - Categories are **soft-managed** (active/inactive). **No hard delete**.

### IV. PV/RV Semantics Are Explicit
- `PV` = **Expense** account codes (e.g., 50, 501…)
- `RV` = **Revenue** account codes (e.g., 40, 401…)
- System must represent category type as `EXPENSE | REVENUE` and validate it end-to-end.

### V. Source of Truth: DB (Audit-Friendly)
- Dashboard/Insights/P&L calculations must use **DB (doc_type=DB) amounts as truth**.
- `CR` is a **commitment** reference only.
- Variance rule:
  - `variance = DB - CR`
  - Under/Over handling uses the **same account_code** as the case/category.

### VI. Chat Is Assistance Only (No Free-Text Truth)
- Gemini (Chat) may only **suggest**.
- Final persisted data must be **structured and validated** (e.g., `category_id`, `requested_amount`, `purpose`, required dimensions).
- Category must be chosen from the **fixed category list**; no free-text category creation.
- Low-confidence flows must fall back to explicit user selection.

### VII. Security, RBAC, and Auditability
- Every API endpoint must enforce **RBAC**.
- All state transitions must be logged in `audit_logs` with who/when/what.
- Data is append-only where possible; sensitive actions must be traceable.

### VIII. No Hard Deletes
- No hard delete for any business entity (cases, categories, documents, payments, attachments).
- Use `status`, `is_active`, or equivalent soft-deactivation.

---

## Architecture & Technology Constraints

### Operational DB
- Use **Cloud SQL (PostgreSQL)** for operational truth.
- Must enforce relational constraints and ACID transactions.
- Required constraint (minimum): `UNIQUE(case_id, doc_type)` for documents.

### File Storage (GCS)
- All PDFs and attachments are stored in **private GCS buckets**.
- Access via **Signed URL** only.

### Analytics (Phase 2)
- BigQuery may be introduced later; until then, dashboards read from Cloud SQL.

---

## Domain Model Constraints (Minimum Set)

### Entities
- `categories`: fixed list, active/inactive, maps to exactly one `account_code`, type `EXPENSE|REVENUE`.
- `cases`: core entity, references category, stores denormalized `account_code`, has a strict status machine.
- `documents`: abstraction for `PS|CR|DB` with `UNIQUE(case_id, doc_type)`.
- `payments`: `DISBURSE|REFUND|ADDITIONAL`.
- `attachments`: `QUOTE|RECEIPT|OTHER`.
- `audit_logs`: immutable audit trail.
- `doc_counters`: atomic numbering for `PS/CR/DB-YYMM-####`.

### Workflow State Machine (v2)
- Allowed case statuses:
  - `DRAFT`
  - `SUBMITTED`
  - `PS_APPROVED` / `PS_REJECTED`
  - `CR_ISSUED`
  - `PAID`
  - `SETTLEMENT_SUBMITTED`
  - `DB_ISSUED`
  - `CLOSED`
  - `CANCELLED`
- Transitions must be validated server-side; no direct status edits.

---

## Development Workflow & Quality Gates

### Branch & PR Rules
- All changes go through PR.
- PR must include:
  - link to the relevant `specs/<feature>/...` artifacts
  - tests for new/changed logic
  - migration scripts if schema changes

### Testing
- Minimum expectations:
  - unit tests for domain rules and RBAC
  - integration tests for key workflows (case → PS → CR → payment → settlement → DB)

### Observability
- Structured logs for all services.
- Errors must include correlation identifiers.

---

## Governance
- This Constitution supersedes all other project practices.
- Any change to the NON-NEGOTIABLE principles requires:
  1) a written amendment
  2) migration plan (if data/model impacted)
  3) explicit approval recorded in the PR
- All reviews must verify Constitution compliance.

**Version**: 2.0.0 | **Ratified**: 2025-12-23 | **Last Amended**: 2025-12-23
34.177.88.104 