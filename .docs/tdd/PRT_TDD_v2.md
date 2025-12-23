### **TDD Version 2**

**Smart Accounting Workflow Web App (Chat-first, Fixed Category, PV/RV) on GCP**

**Version:** 2.0

**Status:** Blueprint for Implementation

**Target Platform:** Google Cloud Platform (GCP)

---

### **0. What changed from TDD v1**

**0.1 Major Changes**

*   **Changed from manual GL Code → "Fixed Category + Auto-map Account Code"**
    *   Users do not see the account codes.
    *   Only the Accounting department can create categories (fixed).
    *   It is always 1 Category → 1 Account Code (for posting).
*   **Changed model from "Request" → "Case-centric"**
    *   1 Case = 1 Category = 1 Account Code = 1 CR (Cash Requisition) = 1 DB (Debit/Settlement Document).
    *   If a user needs to request funds for multiple types of expenses (e.g., books + travel expenses), they must create multiple Cases (multiple documents).
*   **UI changed to "Chat-first + Figma Navigation"**
    *   The Chat View is the main entry point (Conversational Command Center).
    *   Forms + Previews are used for accuracy (audit-friendly).
    *   Includes a Dashboard/Insights/P&L based on the layout in Figma.
*   **Data presentation (Dashboard/P&L) uses the DB as the source of truth.**
    *   The numbers used for display and analysis must primarily come from the DB.
    *   The CR is used only as a "commitment" to calculate variance.
*   **Clearly defined PV/RV**
    *   PV Code = Expense (50, 501…)
    *   RV Code = Revenue (40, 401…)

---

### **1. System Overview (v2 Update)**

A web app for managing financial and accounting workflows by digitizing key documents:

*   **PS** = Spending Approval Form (Finance)
*   **CR** = Cash Requisition Form (Accounting)
*   **DB** = Account Settlement Document (Accounting)

Data is stored in two parts:
*   PDF documents and attachments (uploaded + generated) → stored in GCS.
*   Structured data (cases, categories, numbers, statuses, audit trails) → stored in an Operational DB → used for dashboards/analytics.

**Core UX v2:** Chat-first + Smart Suggestions (Gemini), but the final data must be structured (free text is not accepted as a source of truth).

---

### **2. Actors & Roles (Same as v1 but with added Category Governance permissions)**

*   **Requester**
    *   Creates a Case from Chat or a Form.
    *   Uploads attachments.
    *   Submits settlement information (actual amount/receipts) → moves to "Awaiting Accounting to issue DB" status.
*   **Finance**
    *   Approves/Rejects PS.
    *   Views cases based on their status.
*   **Accounting**
    *   Manages Categories (Create/Deactivate/Update mapping).
    *   Issues CR / Issues DB.
    *   Verifies documents/evidence.
    *   Views variance (DB-CR).
*   **Treasury**
    *   Disburses funds according to the CR.
    *   Receives refunds/makes additional payments in case of under/over-spending (using the same account).
*   **Admin**
    *   Manages users/roles.
    *   Manages additional master data (department, cost center, funding type, etc.).
*   **Executive**
    *   Views Dashboard/Insights/P&L.

---

### **3. Scope (v2)**

**In-Scope (v2)**

*   Complete Workflow: Case → PS → CR → Payment → DB → Close.
*   Fixed Category + PV/RV mapping.
*   Chat View + Form + Preview as per Figma.
*   PDF generation: PS/CR/DB + Refund/Receipt forms (optional).
*   File upload → GCS + signed URL.
*   Dashboard/Insights/P&L (using DB as the source of truth).
*   Audit trail + status timeline.

**Out-of-Scope (v2 initial release)**

*   ERP integration.
*   Multi-company support.
*   Full-featured tax engine.
*   Complex budget/project management (but the design will support it in the future).

---

### **4. UX & UI (Based on Figma) – v2 Spec**

**4.1 Navigation**
*   Dashboard
*   Form
*   Insights
*   Profit and Loss
*   Chat View (Primary)

**4.2 Chat View (Conversational Command Center)**

Used for:
*   **Create case:** "Request 500 Baht for travel to a meeting."
*   **Search:** "Find this month's CRs."
*   **Summary:** "How much are this month's expenses?"
*   **Shortcuts:** As designed (search for CR slips / all expenses / check remaining balance, etc.).

**UX Contract**
*   Gemini only provides "suggestions."
*   Categories must be selected from a fixed list (created by Accounting).
*   Before creating a case, all structured fields must be complete: `category_id`, `requested_amount`, `purpose`, `dept/cost center` (if required).

**4.3 Form + Preview**
*   **Left side:** Fill in structured fields.
*   **Right side:** Preview the document (what will be generated as a PDF).
*   The preview must be enforced to match the PS/CR/DB template for auditing purposes.

---

### **5. Master Data: Category & PV/RV Governance (New in v2)**

**5.1 Category Model**
*   **Category** = What the user sees (human-readable).
*   **Account Code** = What the system records (PV/RV).

**Rules**
*   Categories can only be created/edited by Accounting/Admin roles.
*   It is always 1 Category → 1 Account Code.
*   Categories have an active/inactive status (they are not deleted).

**5.2 PV/RV Definition**
*   **PV Code** = Expense (50, 501…)
*   **RV Code** = Revenue (40, 401…)
*   In v2, the system supports both expenses and revenue, differentiated by `category_type`.

---

### **6. Core Domain Model: Case-centric (New in v2)**

**6.1 Definition**
*   A **Case** is the main unit of the workflow.
*   1 Case = 1 Category = 1 Account Code = 1 CR = 1 DB.

**6.2 Practical example (as per requirements)**
*   A teacher wants to buy books + request travel expenses.
    → Create 2 cases:
        *   Category "Educational Supplies" → PV 501051
        *   Category "Travel Expenses" → PV 501043

---

### **7. Workflow State Machine (v2)**

**7.1 Case Status**
*   `DRAFT`
*   `SUBMITTED` (Awaiting Finance)
*   `PS_APPROVED` / `PS_REJECTED`
*   `CR_ISSUED`
*   `PAID`
*   `SETTLEMENT_SUBMITTED` (Requester submits actual amount/receipts)
*   `DB_ISSUED`
*   `CLOSED`
*   `CANCELLED`

**7.2 Under/Over Rule (v2)**
*   `variance` = DB amount - CR amount.
*   Uses the original `account_code`.
*   Treasury payment uses types:
    *   `DISBURSE` (Pay according to CR)
    *   `REFUND` (Receive refund if DB < CR)
    *   `ADDITIONAL` (Pay extra if DB > CR)
*   Dashboard source of truth: Primarily uses the DB amount.

---

### **8. Data Layer (v2 recommendation)**

**8.1 Operational DB**
*   Recommend **Cloud SQL (PostgreSQL)** for v2 because:
    *   It easily enforces the "1 case per 1 doc type" constraint using `UNIQUE` + `FK`.
    *   Requires clear ACID transactions + audit logs.

**8.2 GCS**
*   Private buckets: `acct-docs-dev` / `acct-docs-prod`.
*   Signed URL for upload/download.

**8.3 Analytics (Phase 2)**
*   **BigQuery** for scaling dashboards/insights.
*   However, for v2, dashboards can start from Cloud SQL first.

---

### **9. Data Model (Logical v2)**

**9.1 `categories` (new)**
*   `id`
*   `name_th`
*   `type` (EXPENSE|REVENUE)
*   `account_code`
*   `is_active`
*   `created_by`, `created_at`

**9.2 `cases` (replaces `cash_requests` as core entity)**
*   `id`
*   `case_no`
*   `category_id`
*   `account_code` (denormalized)
*   `requester_id`
*   `department_id` / `cost_center_id`
*   `funding_type` (OPERATING default; GOV_BUDGET for future)
*   `requested_amount`
*   `status`
*   `created_at`, `updated_at`

**9.3 `documents` (new abstraction for PS/CR/DB)**
*   `id`
*   `case_id`
*   `doc_type` (PS|CR|DB)
*   `doc_no`
*   `amount`
*   `pdf_uri`
*   `created_by`, `created_at`
*   Constraint: `UNIQUE(case_id, doc_type)`

**9.4 `payments`**
*   `id`
*   `case_id`
*   `type` (DISBURSE|REFUND|ADDITIONAL)
*   `amount`
*   `paid_by`
*   `paid_at`
*   `reference_no`

**9.5 `attachments`**
*   `id`
*   `case_id`
*   `type` (QUOTE|RECEIPT|OTHER)
*   `gcs_uri`
*   `uploaded_by`, `uploaded_at`

**9.6 `audit_logs`**
*   `id`
*   `entity_type`/`entity_id`
*   `action`
*   `performed_by`
*   `performed_at`
*   `details_json`

---

### **10. Document Numbering (v2)**

**Format (fixed):**
*   `PS-YYMM-####`
*   `CR-YYMM-####`
*   `DB-YYMM-####`

**Running number policy:**
*   Running numbers are separate for each `doc_type` and `YYMM`.
*   Store a counter in the DB (`doc_counters`) for atomic increment.

---

### **11. API Design (v2)**

**11.1 Category APIs**
*   `GET /api/categories?type=EXPENSE&active=true`
*   `POST /api/categories` (Accounting/Admin)
*   `PATCH /api/categories/{id}` (deactivate/update)

**11.2 Case APIs**
*   `POST /api/cases` (create draft/submit)
*   `POST /api/cases/{id}/submit`
*   `GET /api/cases?status=…`
*   `GET /api/cases/{id}`

**11.3 Workflow APIs**
*   `POST /api/cases/{id}/ps/approve` (Finance)
*   `POST /api/cases/{id}/cr/issue` (Accounting)
*   `POST /api/cases/{id}/payment` (Treasury)
*   `POST /api/cases/{id}/settlement/submit` (Requester)
*   `POST /api/cases/{id}/db/issue` (Accounting)

**11.4 Files**
*   `POST /api/files/signed-url` (upload)
*   `GET /api/files/{doc_id}/download-url` (signed download)

**11.5 Chat (Gemini)**
*   `POST /api/chat`
    *   **input:** user message + context
    *   **output:** intent + suggested categories + missing fields + draft payload

---

### **12. Gemini (Chat) Design (v2)**

**12.1 Principles**
*   Gemini "suggests," it does not make "accounting decisions."
*   Categories must come from the fixed list only.
*   The output of Gemini must be a JSON schema that the system can validate.

**12.2 Retrieval sources**
*   `categories` (fixed master data)
*   User's recent cases
*   Metadata of documents/cases for searching

**12.3 Fail-safe**
*   If confidence is low → let the user select a category from a search list (non-AI).

---

### **13. PDF Generation Service (Same as v1 but linked to `documents` table)**

*   Separate Cloud Run service: `/pdf/generate`
*   **Input:** `template_id` (PS/CR/DB) + case/doc data
*   **Output:** PDF in GCS + `pdf_uri` updated in `documents` table
*   **Idempotency:**
    *   Use `doc_no` as a key to prevent duplicate creation.

---

### **14. Dashboard / Insights / P&L (v2)**

**14.1 Source of truth**
*   Expense/Revenue primarily uses the DB amount (`doc_type=DB`).

**14.2 KPIs (as per Figma)**
*   Total expense (DB-based)
*   Total revenue (DB-based RV)
*   Cash remaining / balance
*   Monthly trend
*   Latest items list
*   Outstanding cases (DB not yet issued)

---

### **15. Security & Compliance (Increased emphasis)**

*   RBAC on every endpoint.
*   Private GCS, signed URLs only.
*   `audit_logs` + Cloud Logging.
*   No hard deletes (use soft delete/status changes).

---

### **16. Future: Government Budget (Supported in the model)**

Add to `cases`:
*   `funding_type`: `OPERATING` | `GOV_BUDGET`
*   `budget_project_id`, `fiscal_year` (optional)

UX:
*   Hidden by default.
*   Enabled only for Accounting/Admin roles or special case types.

---

### **Appendix A: Mapping v1 → v2 (To help the team migrate their understanding)**

*   `cash_requests` (v1) → `cases` (v2)
*   `finance_approvals`/`accounting_crs`/`db_settlements` (v1) → `documents` (v2) + `doc_type`
*   manual `gl_code` (v1) → `category`/`account_code` mapping (v2)
*   Dashboard using a mix of CR/DB (v1) → Dashboard relies on DB (v2)