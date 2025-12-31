# Foundation Specification: PRT Software Accounting Core Domain

## 1. Introduction

This document outlines the foundation specification for the PRT Software Accounting system's core domain. It serves as the primary reference for the system's foundational model, constraints, and policies, ensuring alignment with the project's constitutional principles and the TDD v2 blueprint.

**References:**
*   [.docs/tdd/PRT_TDD_v2.md](.docs/tdd/PRT_TDD_v2.md)
*   [.specify/memory/constitution.md](.specify/memory/constitution.md)

---

## 2. Core Principles

The following non-negotiable principles underpin the PRT software accounting system:

*   **Case-Centric Accounting Model:** A strict one-to-one correspondence: `1 Case = 1 Category = 1 Account Code = 1 CR = 1 DB`. Requests requiring multiple categories must result in multiple distinct cases.
*   **Category Governance:** Categories are fixed and managed exclusively by Accounting/Admin roles. They map uniquely (`1 Category → 1 Account Code`) and are subject to soft-deletion (active/inactive status) rather than hard removal.
*   **PV/RV Semantics:** Explicitly defines `PV` (Expense) and `RV` (Revenue) account codes, ensuring system-wide validation of category types (`EXPENSE | REVENUE`).
*   **Source of Truth: Debit Document (DB):** For all dashboards, insights, and P&L calculations, the `DB` (Debit/Settlement Document) amounts are the ultimate source of truth. `CR` (Cash Requisition) serves solely as a commitment reference for variance calculation.
*   **Chat Is Assistance Only:** The conversational interface (Gemini Chat) provides suggestions and structured input guidance. It never acts as a source of truth; all final persisted data must be structured, validated, and derived from fixed lists where applicable (e.g., categories).
*   **No Hard Deletes:** No business entity (cases, categories, documents, payments, attachments) will be permanently deleted. Instead, soft-deactivation mechanisms (`status`, `is_active`) will be used.

---

## 3. Core Domain Model

The core domain revolves around the `Case` entity, abstracting various documents and maintaining auditability.

### 3.1 Entities

*   **`categories`**: Manages a fixed list of human-readable categories. Each category maps to exactly one `account_code` and has a `type` (`EXPENSE` or `REVENUE`). Includes `is_active` for soft-deactivation.
*   **`cases`**: The central entity representing a single accounting workflow. It references a `category_id`, denormalizes the `account_code`, tracks the `requester_id`, `department_id`, `cost_center_id`, `funding_type`, `requested_amount`, and its current `status`.
*   **`documents`**: An abstraction for `PS` (Spending Approval), `CR` (Cash Requisition), and `DB` (Debit/Settlement Document). Each document is linked to a `case_id`, has a `doc_type`, a unique `doc_no`, an `amount`, and a `pdf_uri` pointing to the generated PDF in GCS.
*   **`payments`**: Records financial transactions related to a case, including `type` (`DISBURSE`, `REFUND`, `ADDITIONAL`), `amount`, `paid_by`, `paid_at`, and `reference_no`.
*   **`attachments`**: Stores metadata for files uploaded by users (quotes, receipts, other). Includes `case_id`, `type` (`QUOTE`, `RECEIPT`, `OTHER`), and `gcs_uri` for the file location.
*   **`audit_logs`**: An immutable trail of all significant system actions and state transitions. Records `entity_type`, `entity_id`, `action`, `performed_by`, `performed_at`, and `details_json`.
*   **`doc_counters`**: Manages atomic, sequential numbering for various document types.

### 3.2 Cloud SQL Schema (Postgres)

#### `categories` table
*   `id` (PK, UUID)
*   `name_th` (VARCHAR, UNIQUE, NOT NULL)
*   `type` (ENUM 'EXPENSE', 'REVENUE', NOT NULL)
*   `account_code` (VARCHAR, UNIQUE, NOT NULL)
*   `is_active` (BOOLEAN, DEFAULT TRUE, NOT NULL)
*   `created_by` (VARCHAR, NOT NULL)
*   `created_at` (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
*   `updated_by` (VARCHAR)
*   `updated_at` (TIMESTAMP WITH TIME ZONE)

#### `cases` table
*   `id` (PK, UUID)
*   `case_no` (VARCHAR, UNIQUE, NOT NULL)
*   `category_id` (FK to `categories.id`, UUID, NOT NULL)
*   `account_code` (VARCHAR, NOT NULL) -- Denormalized from category for immutability
*   `requester_id` (VARCHAR, NOT NULL)
*   `department_id` (VARCHAR)
*   `cost_center_id` (VARCHAR)
*   `funding_type` (ENUM 'OPERATING', 'GOV_BUDGET', DEFAULT 'OPERATING', NOT NULL)
*   `requested_amount` (NUMERIC(18, 2), NOT NULL)
*   `status` (ENUM 'DRAFT', 'SUBMITTED', 'PS_APPROVED', 'PS_REJECTED', 'CR_ISSUED', 'PAID', 'SETTLEMENT_SUBMITTED', 'DB_ISSUED', 'CLOSED', 'CANCELLED', NOT NULL)
*   `created_by` (VARCHAR, NOT NULL)
*   `created_at` (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
*   `updated_by` (VARCHAR)
*   `updated_at` (TIMESTAMP WITH TIME ZONE)

#### `documents` table
*   `id` (PK, UUID)
*   `case_id` (FK to `cases.id`, UUID, NOT NULL)
*   `doc_type` (ENUM 'PS', 'CR', 'DB', NOT NULL)
*   `doc_no` (VARCHAR, UNIQUE, NOT NULL)
*   `amount` (NUMERIC(18, 2), NOT NULL)
*   `pdf_uri` (VARCHAR, NOT NULL) -- GCS URI
*   `created_by` (VARCHAR, NOT NULL)
*   `created_at` (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
*   `updated_by` (VARCHAR)
*   `updated_at` (TIMESTAMP WITH TIME ZONE)
*   **Constraint:** `UNIQUE(case_id, doc_type)`

#### `payments` table
*   `id` (PK, UUID)
*   `case_id` (FK to `cases.id`, UUID, NOT NULL)
*   `type` (ENUM 'DISBURSE', 'REFUND', 'ADDITIONAL', NOT NULL)
*   `amount` (NUMERIC(18, 2), NOT NULL)
*   `paid_by` (VARCHAR, NOT NULL)
*   `paid_at` (TIMESTAMP WITH TIME ZONE, NOT NULL)
*   `reference_no` (VARCHAR)
*   `created_at` (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)

#### `attachments` table
*   `id` (PK, UUID)
*   `case_id` (FK to `cases.id`, UUID, NOT NULL)
*   `type` (ENUM 'QUOTE', 'RECEIPT', 'OTHER', NOT NULL)
*   `gcs_uri` (VARCHAR, NOT NULL)
*   `uploaded_by` (VARCHAR, NOT NULL)
*   `uploaded_at` (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)

#### `audit_logs` table
*   `id` (PK, UUID)
*   `entity_type` (VARCHAR, NOT NULL)
*   `entity_id` (UUID, NOT NULL)
*   `action` (VARCHAR, NOT NULL)
*   `performed_by` (VARCHAR, NOT NULL)
*   `performed_at` (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
*   `details_json` (JSONB)

#### `doc_counters` table
*   `id` (PK, UUID)
*   `doc_prefix` (ENUM 'PS', 'CR', 'DB', NOT NULL)
*   `year_month` (VARCHAR(4), NOT NULL) -- Format 'YYMM'
*   `last_number` (INTEGER, DEFAULT 0, NOT NULL)
*   **Constraint:** `UNIQUE(doc_prefix, year_month)`

---

## 4. Constraints

### 4.1 Core Relational Constraints

*   **Document Uniqueness:** Enforced by a `UNIQUE(case_id, doc_type)` constraint on the `documents` table, ensuring that each case can have at most one PS, one CR, and one DB.
*   **Referential Integrity:** All foreign key relationships (`category_id` in `cases`, `case_id` in `documents`, `payments`, `attachments`) will enforce `ON DELETE RESTRICT` or `ON DELETE NO ACTION` to prevent orphaned records or accidental deletion, aligning with the "No Hard Deletes" principle.

### 4.2 Document Numbering

*   **Format:** Document numbers strictly adhere to `[DOC_TYPE]-YYMM-####` (e.g., `PS-2512-0001`, `CR-2512-0023`).
*   **Policy:** Running numbers are independent for each `doc_type` and `YYMM` combination. The `doc_counters` table will manage atomic increments for generating these numbers.

### 4.3 Non-negotiable Business Rules (Summary)

*   `1 case = 1 category = 1 account_code = 1 CR = 1 DB`.
*   Category assignment is fixed for a case once created and cannot be changed by end-users.
*   Dashboard and P&L reporting must derive their truth from the `DB` document amounts.
*   `PV` (Expense) and `RV` (Revenue) semantics are explicitly defined and enforced by the `category.type` field.
*   No hard deletion of any business entity; soft-deactivation (e.g., `is_active` or `status` changes) is the only allowed method for deprecating or hiding data.
*   Chat functionality serves purely for suggestions and structured data input assistance; it is not a source of truth for business data.

---

## 5. Status Machine (for `cases` entity)

The `cases.status` field will adhere to a strict state machine, with all transitions validated server-side. Direct editing of status is prohibited.

**Allowed Case Statuses:**
*   `DRAFT`
*   `SUBMITTED` (Awaiting Finance approval)
*   `PS_APPROVED`
*   `PS_REJECTED`
*   `CR_ISSUED`
*   `PAID`
*   `SETTLEMENT_SUBMITTED` (Requester submits actual amounts/receipts)
*   `DB_ISSUED`
*   `CLOSED`
*   `CANCELLED`

---

## 6. RBAC Matrix

Role-Based Access Control will be enforced at every API endpoint.

| Role        | Create Case | Upload Attachments | Submit Settlement | Approve/Reject PS | Manage Categories | Issue CR/DB | Disburse Funds | View Dashboard |
| :---------- | :---------- | :----------------- | :---------------- | :---------------- | :---------------- | :---------- | :------------- | :------------- |
| **Requester**   | Yes         | Yes                | Yes               | No                | No                | No          | No             | Yes            |
| **Finance**     | No          | No                 | No                | Yes               | No                | No          | No             | Yes            |
| **Accounting**  | No          | No                 | No                | No                | Yes               | Yes         | No             | Yes            |
| **Treasury**    | No          | No                 | No                | No                | No                | No          | Yes            | Yes            |
| **Admin**       | Yes         | Yes                | Yes               | Yes               | Yes               | Yes         | Yes            | Yes            |
| **Executive**   | No          | No                 | No                | No                | No                | No          | No             | Yes            |

*Note: "Manage Categories" includes create, update, deactivate, and mapping account codes.*

---

## 7. Audit Logs Policy

All state transitions and critical actions within the system must be meticulously recorded in the `audit_logs` table.

*   **Granularity:** Every significant change to a business entity (e.g., case status change, document creation, payment disbursement, category update) must generate an audit log entry.
*   **Immutability:** `audit_logs` records are append-only; once created, they cannot be modified or deleted.
*   **Content:** Each log entry must capture:
    *   `entity_type` (e.g., 'case', 'document', 'category')
    *   `entity_id` (UUID of the affected entity)
    *   `action` (e.g., 'CASE_SUBMITTED', 'PS_APPROVED', 'CATEGORY_DEACTIVATED')
    *   `performed_by` (Identifier of the user or system performing the action)
    *   `performed_at` (Timestamp of the action)
    *   `details_json` (JSONB field for additional contextual information, such as old and new values for changed fields, or specific reasons for an action).
*   **RBAC Integration:** Audit logs will implicitly track RBAC enforcement outcomes, as `performed_by` will indicate the authenticated actor.

---

## 8. GCS Signed URL Policy

All sensitive or user-uploaded files will be stored and accessed securely via Google Cloud Storage (GCS) with strict policy enforcement.

*   **Private Buckets:** All GCS buckets storing application-related documents (PDFs, attachments) will be private. Public access is strictly forbidden.
*   **Signed URLs for Access:**
    *   **Uploads:** Users (or the system on their behalf) will receive a time-limited, pre-signed URL to directly upload files to GCS. The backend service will generate and provide these URLs after initial validation.
    *   **Downloads/Viewing:** Accessing stored files (e.g., viewing a generated PDF or a user-uploaded receipt) will require a time-limited, pre-signed URL generated by the backend. The backend will verify the user's authorization (via RBAC) before generating and providing the signed URL.
*   **No Direct GCS Access:** Application components and end-users will never directly access GCS objects using service account credentials or public URLs. All interactions will be proxied and secured by the backend via signed URLs.

# Specification v3: Voucher System (PV/RV/JV)

## 1. Core Principles
* **Voucher-Based:** All accounting documents are Vouchers (PV, RV, JV).
* **1 Case = 1 PV:** A standard Expense Case results in exactly one Payment Voucher.
* **Receipt Tracking:** Users upload receipts directly to the Case (PV). System tracks `is_receipt_uploaded`.
* **Refunds via RV:** Returned funds are recorded as Receive Vouchers (RV).

## 2. Document Types
* **PV (Payment Voucher):** Expense payment. Generated upon **Finance Approval**.
* **RV (Receive Voucher):** Income/Refund. Generated upon **Recording**.
* **JV (Journal Voucher):** Adjustments/Closing complex cases. Links multiple PVs.

## 3. Data Model Changes
### `cases`
* `deposit_account_id` (FK): For RV, specifies the destination Asset account (Category 101...).
* `is_receipt_uploaded` (Bool): Tracks if physical evidence is uploaded.
* `status`: DRAFT -> SUBMITTED -> APPROVED (Gen PV) -> PAID -> CLOSED.

### `jv_line_items`
* Links a JV Document to multiple `cases` (PVs) to aggregate actual usage vs budget.

## 4. Workflows
* **Expense (Standard):** Create Case -> Submit -> Finance Approve (PV Generated) -> Treasury Pay -> Upload Receipt -> Close.
* **Expense (Over Budget):** ... -> Create New Case (Top-up PV) -> Create JV (Link PV#1 + PV#2) -> Close.
* **Revenue:** Create RV Case -> Select Income Category & Deposit Account -> Save (RV Generated).