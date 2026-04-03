# Implementation Plan: PRT Software Accounting Core Domain Foundation

## 1. Introduction

This document outlines a phased implementation plan for the foundation-core-domain of the PRT Software Accounting system. The plan is tailored for a small backend team utilizing Python, GCP, and Cloud SQL (Postgres), translating the approved [foundation specification](spec.md) into actionable steps. It prioritizes database setup, security, and a minimal viable workflow, ensuring adherence to all non-negotiable constraints.

**References:**
*   [spec.md](spec.md)
*   [.docs/tdd/PRT_TDD_v2.md](../../.docs/tdd/PRT_TDD_v2.md)
*   [constitution.md](../../.specify/memory/constitution.md)

## 2. Constraints (Non-Negotiable Review)

The following constraints must be strictly adhered to throughout implementation:
*   `1 Case = 1 Category = 1 Account Code = 1 CR = 1 DB`
*   Categories are fixed and managed only by Accounting/Admin roles.
*   Dashboard/P&L truth must be derived from `DB` (doc_type=DB) amounts.
*   Database must enforce `UNIQUE(case_id, doc_type)` on documents.
*   Role-Based Access Control (RBAC) must be enforced on every API endpoint.
*   No hard deletes for any business entity; soft-deletion mechanisms must be used.

## 3. Implementation Phases

### Phase 1: Database Schema and Migrations

**Objective:** Establish the foundational database schema in Cloud SQL (Postgres) with all tables, columns, constraints, and relationships as defined in the foundation specification.

**Deliverables:**
*   **Database Migration Scripts:** Idempotent scripts (e.g., using Alembic or similar) to create all specified tables (`categories`, `cases`, `documents`, `payments`, `attachments`, `audit_logs`, `doc_counters`). Ensure the `cases` table includes a `purpose` field (TEXT) for audit-friendly descriptions.
*   **Schema Enforcement:** Implementation of all `NOT NULL`, `UNIQUE` (especially `UNIQUE(case_id, doc_type)`), `DEFAULT` values, `ENUM` types (or equivalent checks), and Foreign Key constraints with `ON DELETE RESTRICT/NO ACTION`.
*   **Initial Data Seed Script:** Script to populate essential initial data (e.g., base categories if required for testing).

**Definition of Done:**
*   All tables and columns specified in `specs/foundation-core-domain/spec.md` are accurately created in a Cloud SQL Postgres instance.
*   All primary keys, foreign keys, `UNIQUE` constraints (including `UNIQUE(case_id, doc_type)`), `NOT NULL` constraints, and `DEFAULT` values are correctly applied.
*   ENUM types are correctly implemented (e.g., using Postgres `ENUM` types or application-level validation).
*   Database migration tools are configured and functional, allowing for reproducible schema evolution.
*   Unit tests for database models (if using an ORM) pass successfully.

### Phase 2: Authentication and RBAC Middleware

**Objective:** Implement robust authentication and a flexible RBAC system that enforces permissions on all API endpoints as per the RBAC Matrix in the foundation specification.

**Deliverables:**
*   **User/Role Management:** Basic entities/mechanisms to define users and assign roles (e.g., `Requester`, `Finance`, `Accounting`, `Treasury`, `Admin`, `Executive`). This might involve integrating with an existing identity provider or a minimal in-app solution for initial setup.
*   **Authentication Mechanism:** Secure user authentication (e.g., JWT-based, OAuth, etc.).
*   **RBAC Middleware/Decorators:** A system-wide middleware or decorator pattern that intercepts API requests, identifies the authenticated user's role(s), and checks if they have the necessary permissions for the requested action and resource. This must cover all defined roles and their permissions in the RBAC matrix.
*   **Unauthorized Access Handling:** Graceful handling and appropriate error responses for unauthorized access attempts.

**Definition of Done:**
*   Users can authenticate securely with the system.
*   Roles can be assigned to users.
*   A generic RBAC middleware or decorator is implemented and integrated into the API framework.
*   Access to *at least one* example endpoint for each role (e.g., Requester can create a case, Finance can approve a PS) is correctly restricted/permitted according to the RBAC matrix.
*   Attempts to access unauthorized resources result in a `403 Forbidden` error.
*   Unit tests for authentication and RBAC logic pass successfully.

### Phase 3: Minimal Workflow APIs (Happy Path)

**Objective:** Implement the core API endpoints to support a single, happy-path workflow of a case, from creation to final settlement, adhering to the `1 Case = 1 Category = 1 Account Code = 1 CR = 1 DB` constraint and status machine.

**Deliverables:**
*   **Category Management APIs (Admin/Accounting only):**
    *   `POST /api/categories`: Create a new category.
    *   `GET /api/categories`: List active categories (for Requester to select).
    *   `PATCH /api/categories/{id}`: Update/deactivate a category.
*   **Case Creation API (`Requester`):**
    *   `POST /api/cases`: Create a new case in `DRAFT` status, ensuring `category_id` maps to a valid `account_code` and that no other `CR` or `DB` documents exist for this case (initial constraint check).
*   **Case Submission API (`Requester`):**
    *   `POST /api/cases/{id}/submit`: Move a `DRAFT` case to `SUBMITTED` status.
*   **PS Approval/Rejection APIs (`Finance`):**
    *   `POST /api/cases/{id}/ps/approve`: Create a `documents` entry for `doc_type=PS` and transition case status to `PS_APPROVED`.
    *   `POST /api/cases/{id}/ps/reject`: Transition case status to `PS_REJECTED`.
*   **CR Issuance API (`Accounting`):**
    *   `POST /api/cases/{id}/cr/issue`: Create a `documents` entry for `doc_type=CR` (ensuring `UNIQUE(case_id, doc_type)`), generate `doc_no`, and transition case status to `CR_ISSUED`.
*   **Payment Disbursement API (`Treasury`):**
    *   `POST /api/cases/{id}/payment`: Create a `payments` entry for `type=DISBURSE` and transition case status to `PAID`.
*   **Settlement Submission API (`Requester`):**
    *   `POST /api/cases/{id}/settlement/submit`: Transition case status to `SETTLEMENT_SUBMITTED`.
*   **DB Issuance API (`Accounting`):**
    *   `POST /api/cases/{id}/db/issue`: Create a `documents` entry for `doc_type=DB` (ensuring `UNIQUE(case_id, doc_type)`), generate `doc_no`, and transition case status to `DB_ISSUED`.
*   **Case Closing API (Accounting/Admin):**
    *   `POST /api/cases/{id}/close`: Transition case status from `DB_ISSUED` to `CLOSED`.
*   **Get Case Details API:**
    *   `GET /api/cases/{id}`: Retrieve full details of a case including associated documents.

**Definition of Done:**
*   All specified API endpoints are implemented and accessible via defined routes.
*   Each API endpoint correctly enforces RBAC based on the `spec.md` matrix.
*   The `1 Case = 1 Category = 1 Account Code = 1 CR = 1 DB` constraint is programmatically enforced (e.g., a case cannot proceed if a CR already exists).
*   The `UNIQUE(case_id, doc_type)` constraint is respected during document creation (CR, DB).
*   Case status transitions strictly follow the state machine defined in `spec.md`.
*   Document numbers are generated correctly using the `doc_counters` logic (`[DOC_TYPE]-YYMM-####`).
*   Unit and integration tests covering the happy-path flow for each implemented API and status transition pass successfully.

### Phase 4: Audit Logging Integration

**Objective:** Integrate the audit logging policy into all relevant API endpoints and service logic to capture significant system actions and state changes.

**Deliverables:**
*   **Audit Logging Service/Utility:** A dedicated module or function to record events to the `audit_logs` table, adhering to the specified schema (`entity_type`, `entity_id`, `action`, `performed_by`, `performed_at`, `details_json`).
*   **API/Service Layer Integration:** Integration points within each relevant API endpoint (from Phase 3 and any new ones) to automatically log actions (e.g., case creation, status changes, document issuance, category updates).
*   **Contextual Logging:** Ensure `performed_by` is correctly captured from the authenticated user and `details_json` includes relevant `old_value`/`new_value` for updates.

**Definition of Done:**
*   The `audit_logs` table accurately records all significant state changes and actions performed via the implemented APIs.
*   Each audit log entry contains correct `entity_type`, `entity_id`, `action`, `performed_by` (authenticated user ID), and `performed_at`.
*   `details_json` captures meaningful context for the logged action (e.g., case status transition details).
*   No sensitive information is logged in clear text within `details_json` or other audit fields.
*   Unit tests specifically for the audit logging utility pass.

### Phase 5: GCS Signed URL Services

**Objective:** Implement secure services for generating GCS Signed URLs for both uploading and downloading attachments, adhering to the policy of no direct GCS access.

**Deliverables:**
*   **Signed URL Generation Service:** A backend service endpoint (`POST /api/files/signed-url`) that generates a time-limited signed URL for uploading a file to a specific GCS bucket/path.
    *   This service should validate the request (e.g., file type, user permissions) before generating the URL.
*   **Signed Download URL Service:** A backend service endpoint (`GET /api/files/{doc_id}/download-url` or similar) that generates a time-limited signed URL for downloading an existing file from GCS.
    *   This service *must* perform an RBAC check to ensure the requesting user is authorized to access the specific document (`doc_id`).
*   **Attachment APIs:**
    *   `POST /api/cases/{id}/attachments`: Record metadata for an attachment (e.g., `type`, `gcs_uri` obtained from signed upload) after a successful GCS upload. 
*   **GCS Bucket Configuration:** Ensure GCS buckets are configured for private access and appropriate service account permissions for signed URL generation.

**Definition of Done:**
*   API endpoints exist to securely request signed URLs for both file uploads and downloads.
*   Signed upload URLs correctly allow direct upload to GCS, and the metadata (e.g., `gcs_uri`) is stored in the `attachments` table.
*   Signed download URLs correctly provide temporary access to GCS objects.
*   RBAC checks are enforced before generating signed download URLs, preventing unauthorized access to files.
*   No direct GCS access is permitted from client-side or non-authorized backend components.
*   Unit and integration tests for signed URL generation and usage (simulating upload/download) pass successfully.

### Phase 6: Happy-Path Integration Test

**Objective:** Develop an end-to-end integration test that simulates a complete, successful workflow, validating all implemented phases.

**Deliverables:**
*   **End-to-End Test Script:** A comprehensive automated test that:
    1.  Creates a user with the `Requester` role.
    2.  Creates a user with the `Finance` role.
    3.  Creates a user with the `Accounting` role.
    4.  Creates a user with the `Treasury` role.
    5.  As `Accounting`, creates and activates a `Category`.
    6.  As `Requester`, creates a `Case`.
    7.  As `Requester`, submits the `Case`.
    8.  As `Finance`, approves the `PS` (document generated, status updated).
    9.  As `Accounting`, issues the `CR` (document generated, `UNIQUE(case_id, doc_type)` enforced, status updated).
    10. As `Treasury`, disburses payment (payment recorded, status updated).
    11. As `Requester`, submits settlement (status updated).
    12. As `Accounting`, issues the `DB` (document generated, `UNIQUE(case_id, doc_type)` enforced, status updated).
    13. As `Accounting` (or `Admin`), closes the Case (status updated to `CLOSED`).
    14. Verifies final `Case` status is `CLOSED`.
    15. Verifies all intermediate `documents`, `payments`, and `attachments` metadata exist and are correctly linked.
    16. Verifies all expected `audit_logs` entries for the entire workflow are present and correctly detailed.
    17. Verifies that attempting to create a second `CR` or `DB` for the same case fails with an appropriate error.
    18. Verifies that `DB` amounts are available for dashboard-like queries.

**Definition of Done:**
*   The end-to-end integration test runs successfully without errors.
*   The test covers all key API interactions and state transitions for a complete happy-path workflow.
*   All non-negotiable constraints are explicitly validated within the test (e.g., document uniqueness, RBAC enforcement where applicable within the flow).
*   Database state after the test reflects the expected final state of the `Case` and all related entities.
*   The audit trail is complete and accurate for the simulated workflow.
*   The test can be easily re-run in a clean environment.
