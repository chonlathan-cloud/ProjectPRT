# Actionable Engineering Tasks: PRT Software Accounting Core Domain Foundation

This document breaks down the implementation plan for the PRT Software Accounting Core Domain into small, actionable engineering tasks, suitable for a small backend team. Each task is designed to be completed within 1-2 days and includes objectives, acceptance criteria, dependencies, and test requirements.

**References:**
*   [specs/foundation-core-domain/spec.md](specs/foundation-core-domain/spec.md)
*   [specs/foundation-core-domain/plan.md](specs/foundation-core-domain/plan.md)
*   [.docs/tdd/PRT_TDD_v2.md](../../.docs/tdd/PRT_TDD_v2.md)
*   [.specify/memory/constitution.md](../../.specify/memory/constitution.md)

## Phase 1: Database Schema and Migrations

### Task 1.1: Setup Cloud SQL and Migration Tooling
**Objective:** Configure a Cloud SQL PostgreSQL instance for development and integrate a database migration tool (e.g., Alembic for Python).
**Acceptance Criteria:**
*   A Cloud SQL PostgreSQL instance is provisioned and accessible from the development environment.
*   A Python-based migration tool (e.g., Alembic) is integrated into the project.
*   Basic configuration for connecting to the database is complete.
*   A README entry guides developers on how to run migrations locally.
**Dependencies:** None
**Test Requirements:**
*   Unit: Migration tool initialization and configuration tests.

### Task 1.2: Implement `categories` and `doc_counters` Schema
**Objective:** Create migration scripts for the `categories` and `doc_counters` tables, including all columns, types, unique constraints, and enum types.
**Acceptance Criteria:**
*   Migration scripts for `categories` table (id, name_th, type, account_code, is_active, created_by, created_at, updated_by, updated_at) are created.
*   Migration scripts for `doc_counters` table (id, doc_prefix, year_month, last_number) are created.
*   `UNIQUE` constraints for `categories.name_th`, `categories.account_code`, and `doc_counters.(doc_prefix, year_month)` are defined.
*   `ENUM` types (`EXPENSE`/`REVENUE` for `categories.type`, `PS`/`CR`/`DB` for `doc_counters.doc_prefix`) are correctly implemented.
*   `is_active` defaults to `TRUE` in `categories`.
*   `last_number` defaults to `0` in `doc_counters`.
**Dependencies:** Task 1.1
**Test Requirements:**
*   Unit: Tests verify `categories` and `doc_counters` table structures and constraints after migration.

### Task 1.3: Implement `cases` Schema
**Objective:** Create migration scripts for the `cases` table, including all columns, types, and foreign key references.
**Acceptance Criteria:**
*   Migration scripts for `cases` table (id, case_no, category_id, account_code, requester_id, department_id, cost_center_id, funding_type, requested_amount, purpose, status, created_by, created_at, updated_by, updated_at) are created.
*   `purpose` is required (NOT NULL) and stored as TEXT for audit-friendly descriptions.
*   `category_id` has a foreign key constraint to `categories.id` (`ON DELETE RESTRICT`).
*   `case_no` has a `UNIQUE` constraint.
*   `ENUM` type for `cases.status` (DRAFT, SUBMITTED, etc.) is correctly implemented.
*   `funding_type` defaults to `OPERATING`.
**Dependencies:** Task 1.2
**Test Requirements:**
*   Unit: Tests verify `cases` table structure, constraints, and FK to `categories` after migration.

### Task 1.4: Implement `documents` Schema
**Objective:** Create migration scripts for the `documents` table, including all columns, types, unique constraints, and foreign key references.
**Acceptance Criteria:**
*   Migration scripts for `documents` table (id, case_id, doc_type, doc_no, amount, pdf_uri, created_by, created_at, updated_by, updated_at) are created.
*   `case_id` has a foreign key constraint to `cases.id` (`ON DELETE RESTRICT`).
*   `doc_no` has a `UNIQUE` constraint.
*   `doc_type` has an `ENUM` type (PS, CR, DB).
*   **Crucially, `UNIQUE(case_id, doc_type)` constraint is implemented.**
**Dependencies:** Task 1.3
**Test Requirements:**
*   Unit: Tests verify `documents` table structure, constraints, and FK to `cases` after migration. Test specifically for `UNIQUE(case_id, doc_type)`.

### Task 1.5: Implement `payments` and `attachments` Schema
**Objective:** Create migration scripts for the `payments` and `attachments` tables, including all columns, types, and foreign key references.
**Acceptance Criteria:**
*   Migration scripts for `payments` table (id, case_id, type, amount, paid_by, paid_at, reference_no, created_at) are created.
*   Migration scripts for `attachments` table (id, case_id, type, gcs_uri, uploaded_by, uploaded_at) are created.
*   `case_id` in both tables has a foreign key constraint to `cases.id` (`ON DELETE RESTRICT`).
*   `ENUM` types for `payments.type` and `attachments.type` are correctly implemented.
**Dependencies:** Task 1.3
**Test Requirements:**
*   Unit: Tests verify `payments` and `attachments` table structures, constraints, and FKs to `cases` after migration.

### Task 1.6: Implement `audit_logs` Schema
**Objective:** Create migration scripts for the `audit_logs` table, including all columns, types, and `JSONB` field.
**Acceptance Criteria:**
*   Migration scripts for `audit_logs` table (id, entity_type, entity_id, action, performed_by, performed_at, details_json) are created.
*   `details_json` column is of type `JSONB`.
*   `performed_at` defaults to current timestamp.
**Dependencies:** Task 1.1
**Test Requirements:**
*   Unit: Tests verify `audit_logs` table structure and `JSONB` type after migration.

### Task 1.7: Initial Data Seed Script
**Objective:** Create a script to seed initial data, primarily for testing purposes, focusing on at least one active category.
**Acceptance Criteria:**
*   A script exists that can be run to seed the database with a minimal set of data.
*   At least one `category` with `is_active = TRUE` is created.
*   The script is idempotent and can be run multiple times without issues.
**Dependencies:** All schema migration tasks (1.2-1.6)
**Test Requirements:**
*   Integration: After running the seed script, verify that the seeded data exists in the database.

## Phase 2: Authentication and RBAC Middleware

### Task 2.1: Basic User and Role Management Setup
**Objective:** Define basic data models or configuration for users and their roles within the application, and integrate a basic authentication mechanism.
**Acceptance Criteria:**
*   Data models for `User` and `Role` are defined (can be in-memory for this task, or simple DB tables if deemed quicker).
*   A mechanism to assign roles to users is established.
*   A basic authentication flow (e.g., mock user login, or JWT token generation/validation) is implemented.
**Dependencies:** Phase 1 (if using DB for user/role storage)
**Test Requirements:**
*   Unit: Test user creation, role assignment, and a successful/failed authentication attempt.

### Task 2.2: RBAC Middleware Implementation
**Objective:** Develop a Python middleware or decorator to intercept API requests, identify the authenticated user's roles, and check against required permissions.
**Acceptance Criteria:**
*   A reusable RBAC middleware or decorator is implemented that can be applied to API endpoints.
*   The middleware can extract user roles from the authenticated context.
*   A permission mapping mechanism (e.g., a dictionary, DB table) is defined, linking actions to roles.
*   When applied, the middleware allows requests for permitted roles and rejects (with 403) for unpermitted roles.
**Dependencies:** Task 2.1
**Test Requirements:**
*   Unit: Tests for RBAC middleware: a) request with sufficient permissions passes, b) request with insufficient permissions fails with 403, c) unauthenticated request fails.

## Phase 3: Minimal Workflow APIs (Happy Path)

### Task 3.1: Category Management APIs
**Objective:** Implement API endpoints for creating, listing, and updating/deactivating categories, enforcing RBAC for Accounting/Admin roles.
**Acceptance Criteria:**
*   `POST /api/categories` endpoint is implemented and accessible only by `Accounting`/`Admin` roles. It creates a new category with a unique `name_th` and `account_code`.
*   `GET /api/categories` endpoint is implemented. It lists active categories and can be accessed by all roles.
*   `PATCH /api/categories/{id}` endpoint is implemented and accessible only by `Accounting`/`Admin` roles. It allows updating `name_th`, `account_code`, `type`, and `is_active`.
*   Deactivating a category (`is_active = FALSE`) does not hard delete it.
**Dependencies:** Task 1.2, Task 2.2
**Test Requirements:**
*   Unit: Test category creation, listing, and update/deactivation via API calls.
*   Unit: Test RBAC enforcement for these endpoints (e.g., Requester cannot create/update categories).

### Task 3.2: Implement `doc_counters` Utility
**Objective:** Create a utility function to atomically generate document numbers based on `doc_counters` table, adhering to `[DOC_TYPE]-YYMM-####` format.
**Acceptance Criteria:**
*   A Python utility function `generate_doc_no(doc_type: str)` exists.
*   This function fetches/updates `last_number` for the given `doc_type` and current `YYMM` from `doc_counters` table atomically.
*   It returns a formatted string like `PS-YYMM-####`.
*   It correctly handles increments for new `YYMM` combinations.
**Dependencies:** Task 1.2
**Test Requirements:**
*   Unit: Test `generate_doc_no` for single and concurrent calls, verifying unique and correctly formatted numbers.
*   Unit: Test behavior at the start of a new month/year to ensure `YYMM` reset and `last_number` starts from 1.

### Task 3.3: Case Creation API (`POST /api/cases`)
**Objective:** Implement the API for a Requester to create a new case in `DRAFT` status.
**Acceptance Criteria:**
*   `POST /api/cases` endpoint is implemented and accessible by `Requester`/`Admin` roles.
*   It requires `category_id`, `requested_amount`, and `purpose` (required), and ensures `category_id` is active and valid.
*   A new case is created in the `cases` table with `status = DRAFT`.
*   The `account_code` is correctly denormalized from the selected category.
*   **Enforce `1 Case = 1 Category = 1 Account Code` at creation.**
**Dependencies:** Task 1.3, Task 2.2, Task 3.1
**Test Requirements:**
*   Unit: Test successful case creation with valid data.
*   Unit: Test case creation with invalid `category_id` or inactive category.
*   Unit: Test RBAC enforcement for case creation.

### Task 3.4: Case Submission API (`POST /api/cases/{id}/submit`)
**Objective:** Implement the API for a Requester to submit a `DRAFT` case to `SUBMITTED` status.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/submit` endpoint is implemented and accessible by `Requester`/`Admin` roles for their own cases.
*   It validates that the case exists and is in `DRAFT` status.
*   The case `status` is updated to `SUBMITTED`.
**Dependencies:** Task 1.3, Task 2.2, Task 3.3
**Test Requirements:**
*   Unit: Test successful submission of a DRAFT case.
*   Unit: Test submission of a non-DRAFT case fails.
*   Unit: Test RBAC for submission (e.g., Requester cannot submit another user's case).

### Task 3.5: PS Approval/Rejection APIs (`Finance`)
**Objective:** Implement APIs for Finance to approve or reject a `SUBMITTED` case, creating a PS document on approval.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/ps/approve` endpoint is implemented and accessible by `Finance`/`Admin` roles.
*   It validates that the case exists and is in `SUBMITTED` status.
*   On approval, a `documents` entry for `doc_type=PS` is created (using `generate_doc_no`), and `cases.status` is updated to `PS_APPROVED`.
*   `POST /api/cases/{id}/ps/reject` endpoint is implemented and accessible by `Finance`/`Admin` roles. `cases.status` is updated to `PS_REJECTED`.
**Dependencies:** Task 1.4, Task 2.2, Task 3.2, Task 3.4
**Test Requirements:**
*   Unit: Test successful PS approval/rejection.
*   Unit: Test approval/rejection of cases in incorrect statuses fails.
*   Unit: Test `UNIQUE(case_id, doc_type)` prevents duplicate PS documents.
*   Unit: Test RBAC enforcement for these endpoints.

### Task 3.6: CR Issuance API (`Accounting`)
**Objective:** Implement API for Accounting to issue a CR for `PS_APPROVED` cases, enforcing `UNIQUE(case_id, doc_type)`.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/cr/issue` endpoint is implemented and accessible by `Accounting`/`Admin` roles.
*   It validates that the case exists and is in `PS_APPROVED` status.
*   A `documents` entry for `doc_type=CR` is created (using `generate_doc_no`).
*   **The `UNIQUE(case_id, doc_type)` constraint for CR is enforced.**
*   `cases.status` is updated to `CR_ISSUED`.
**Dependencies:** Task 1.4, Task 2.2, Task 3.2, Task 3.5
**Test Requirements:**
*   Unit: Test successful CR issuance.
*   Unit: Test CR issuance for cases in incorrect statuses fails.
*   Unit: Test `UNIQUE(case_id, doc_type)` prevents duplicate CR documents.
*   Unit: Test RBAC enforcement.

### Task 3.7: Payment Disbursement API (`Treasury`)
**Objective:** Implement API for Treasury to disburse funds for `CR_ISSUED` cases.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/payment` endpoint is implemented and accessible by `Treasury`/`Admin` roles.
*   It validates that the case exists and is in `CR_ISSUED` status.
*   A `payments` entry for `type=DISBURSE` is created.
*   `cases.status` is updated to `PAID`.
**Dependencies:** Task 1.5, Task 2.2, Task 3.6
**Test Requirements:**
*   Unit: Test successful payment disbursement.
*   Unit: Test disbursement for cases in incorrect statuses fails.
*   Unit: Test RBAC enforcement.

### Task 3.8: Settlement Submission API (`Requester`)
**Objective:** Implement API for Requester to submit settlement details for `PAID` cases.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/settlement/submit` endpoint is implemented and accessible by `Requester`/`Admin` roles for their own cases.
*   It validates that the case exists and is in `PAID` status.
*   `cases.status` is updated to `SETTLEMENT_SUBMITTED`.
**Dependencies:** Task 1.3, Task 2.2, Task 3.7
**Test Requirements:**
*   Unit: Test successful settlement submission.
*   Unit: Test submission for cases in incorrect statuses fails.
*   Unit: Test RBAC enforcement.

### Task 3.9: DB Issuance API (`Accounting`)
**Objective:** Implement API for Accounting to issue a DB for `SETTLEMENT_SUBMITTED` cases, enforcing `UNIQUE(case_id, doc_type)`.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/db/issue` endpoint is implemented and accessible by `Accounting`/`Admin` roles.
*   It validates that the case exists and is in `SETTLEMENT_SUBMITTED` status.
*   A `documents` entry for `doc_type=DB` is created (using `generate_doc_no`).
*   **The `UNIQUE(case_id, doc_type)` constraint for DB is enforced.**
*   `cases.status` is updated to `DB_ISSUED`.
*   **Non-negotiable: Dashboard truth = DB** - the DB document created here is the source of truth for reporting.
**Dependencies:** Task 1.4, Task 2.2, Task 3.2, Task 3.8
**Test Requirements:**
*   Unit: Test successful DB issuance.
*   Unit: Test DB issuance for cases in incorrect statuses fails.
*   Unit: Test `UNIQUE(case_id, doc_type)` prevents duplicate DB documents.
*   Unit: Test RBAC enforcement.

### Task 3.10: Case Closing API (`Accounting`/`Admin`)
**Objective:** Implement API for Accounting/Admin to close a `DB_ISSUED` case.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/close` endpoint is implemented and accessible by `Accounting`/`Admin` roles.
*   It validates that the case exists and is in `DB_ISSUED` status.
*   `cases.status` is updated to `CLOSED`.
**Dependencies:** Task 1.3, Task 2.2, Task 3.9
**Test Requirements:**
*   Unit: Test successful case closing.
*   Unit: Test closing a case in an incorrect status fails.
*   Unit: Test RBAC enforcement.

### Task 3.11: Get Case Details API (`GET /api/cases/{id}`)
**Objective:** Implement an API to retrieve comprehensive details of a specific case, including all associated documents, payments, and attachments.
**Acceptance Criteria:**
*   `GET /api/cases/{id}` endpoint is implemented and accessible by all roles who have access to the case (e.g., if requester owns it, if finance approved it, etc. - a simplified initial RBAC can be 'any authenticated user').
*   It returns the case object along with its related `documents`, `payments`, and `attachments`.
*   Handles cases where no related entities exist gracefully.
**Dependencies:** All previous tasks in Phase 3
**Test Requirements:**
*   Unit: Test retrieval of a fully populated case.
*   Unit: Test retrieval of a case with no associated documents/payments/attachments.
*   Unit: Test RBAC for case viewing.

## Phase 4: Audit Logging Integration

### Task 4.1: Develop Audit Logging Utility
**Objective:** Create a reusable Python utility to record audit log entries into the `audit_logs` table.
**Acceptance Criteria:**
*   A Python function, e.g., `log_audit_event(entity_type, entity_id, action, performed_by, details_json=None)` is implemented.
*   This function successfully inserts records into the `audit_logs` table with correct data types.
*   `performed_at` is automatically set to the current timestamp.
**Dependencies:** Task 1.6
**Test Requirements:**
*   Unit: Test `log_audit_event` inserts a record correctly into the database.
*   Unit: Test with and without `details_json`.

### Task 4.2: Integrate Audit Logging into Category Management APIs
**Objective:** Add audit logging to the category creation and update/deactivation APIs.
**Acceptance Criteria:**
*   `POST /api/categories` generates an `audit_logs` entry for `CATEGORY_CREATED`.
*   `PATCH /api/categories/{id}` generates an `audit_logs` entry for `CATEGORY_UPDATED` or `CATEGORY_DEACTIVATED`, with `details_json` reflecting the changes.
**Dependencies:** Task 3.1, Task 4.1
**Test Requirements:**
*   Integration: Create/update a category and verify corresponding entries in `audit_logs` table.

### Task 4.3: Integrate Audit Logging into Case Workflow APIs
**Objective:** Add audit logging to all case-related workflow APIs (creation, submission, approvals, issuance, payments, settlement, closing).
**Acceptance Criteria:**
*   Each API in Tasks 3.3 through 3.10 generates appropriate `audit_logs` entries (e.g., `CASE_CREATED`, `CASE_SUBMITTED`, `PS_APPROVED`, `CR_ISSUED`, `PAYMENT_DISBURSED`, `SETTLEMENT_SUBMITTED`, `DB_ISSUED`, `CASE_CLOSED`).
*   `performed_by` in each log reflects the authenticated user performing the action.
*   `details_json` captures relevant context for each event (e.g., old status, new status, document numbers).
**Dependencies:** Tasks 3.3-3.10, Task 4.1
**Test Requirements:**
*   Integration: Perform a full happy-path workflow and verify all expected audit log entries are present and correct.

## Phase 5: GCS Signed URL Services

### Task 5.1: Configure GCS Buckets and Service Account
**Objective:** Set up private GCS buckets and a service account with necessary permissions for signed URL generation.
**Acceptance Criteria:**
*   Development and production GCS buckets are created (e.g., `acct-docs-dev`, `acct-docs-prod`).
*   Buckets are configured for private access.
*   A GCP service account with `storage.object.creator` and `storage.object.viewer` (or equivalent for signed URLs) roles on these buckets is created.
*   The service account key is securely configured in the application environment.
**Dependencies:** None
**Test Requirements:**
*   Manual: Verify bucket access is restricted and service account can perform required operations.

### Task 5.2: Implement Signed URL Generation Service (Upload)
**Objective:** Develop a backend service to generate pre-signed URLs for direct file uploads to GCS.
**Acceptance Criteria:**
*   `POST /api/files/signed-url` endpoint is implemented and accessible by `Requester`/`Admin` roles.
*   It takes parameters like `file_name`, `content_type`, and returns a time-limited signed URL for uploading.
*   The generated URL allows direct upload to the configured private GCS bucket.
*   The service performs basic validation (e.g., allowed file types) before generating the URL.
**Dependencies:** Task 2.2, Task 5.1
**Test Requirements:**
*   Unit: Test signed URL generation for valid requests.
*   Unit: Test signed URL generation for invalid requests (e.g., disallowed file type).
*   Integration: Use a generated signed URL to upload a dummy file to GCS and verify it appears in the private bucket.

### Task 5.3: Implement Signed URL Generation Service (Download)
**Objective:** Develop a backend service to generate pre-signed URLs for downloading files from GCS, enforcing RBAC.
**Acceptance Criteria:**
*   `GET /api/files/{doc_id}/download-url` endpoint is implemented.
*   It retrieves the `gcs_uri` from the `documents` or `attachments` table based on `doc_id`.
*   It generates a time-limited signed URL for downloading the file from GCS.
*   **Crucially, it performs an RBAC check to ensure the authenticated user is authorized to download this specific `doc_id` before generating the URL.**
**Dependencies:** Task 2.2, Task 5.1, Task 1.4, Task 1.5
**Test Requirements:**
*   Unit: Test signed download URL generation for authorized users.
*   Unit: Test signed download URL generation fails for unauthorized users (RBAC).
*   Integration: Use a generated signed URL to download an existing dummy file from GCS and verify content.

### Task 5.4: Integrate Attachment APIs
**Objective:** Implement API for `Requester` to associate uploaded attachments with a case after successful GCS upload.
**Acceptance Criteria:**
*   `POST /api/cases/{id}/attachments` endpoint is implemented and accessible by `Requester`/`Admin` roles for their cases.
*   It takes `case_id`, `type`, and `gcs_uri` (obtained from a prior signed upload).
*   A new entry is created in the `attachments` table.
**Dependencies:** Task 1.5, Task 2.2, Task 5.2
**Test Requirements:**
*   Unit: Test successful attachment metadata recording.
*   Unit: Test RBAC enforcement for this endpoint.

## Phase 6: Happy-Path Integration Test

### Task 6.1: Develop User & Role Test Data Setup
**Objective:** Create a utility to quickly set up test users with specific roles for the integration test.
**Acceptance Criteria:**
*   A utility function `create_test_user(role: str)` exists that creates a user and assigns the specified role.
*   The utility returns credentials or an authentication token for the created user.
*   It can create users with `Requester`, `Finance`, `Accounting`, `Treasury`, `Admin` roles.
**Dependencies:** Task 2.1
**Test Requirements:**
*   Unit: Verify creation of users with correct roles and retrievable authentication tokens.

### Task 6.2: Implement End-to-End Happy Path Integration Test
**Objective:** Write a comprehensive integration test that simulates the entire happy-path workflow from case creation to closing, validating all system components.
**Acceptance Criteria:**
*   An integration test script simulates the full workflow as described in Phase 6 of `plan.md`.
*   It uses the test users created in Task 6.1.
*   It makes sequential API calls corresponding to each step of the workflow.
*   It asserts that case statuses transition correctly at each step.
*   It asserts the creation and uniqueness of all `documents` (PS, CR, DB).
*   It asserts that `payments` and `attachments` metadata are recorded.
*   It asserts that all expected `audit_logs` entries are present and correct for the entire flow.
*   It specifically tests that attempting to create a second CR or DB for the same case fails with a uniqueness error.
*   The test runs successfully in a clean test environment.
**Dependencies:** All tasks from Phase 3, Task 4.3, Task 5.4, Task 6.1
**Test Requirements:**
*   Integration: The test itself is the primary verification. It must pass without errors.


## Phase 3: Voucher System Refactor (Priority High)

### Database & Models
- [ ] **T3.1** Run Alembic migration `refactor_voucher_system` to update DB schema.
- [ ] **T3.2** Update SQLAlchemy models in `app/models.py`:
    - Rename/Update `DocumentType` Enum (PV, RV, JV).
    - Update `CaseStatus` Enum.
    - Add `deposit_account_id` and `is_receipt_uploaded` to `Case` model.
    - Add `JVLineItem` model.

### Logic Refactoring (Backend)
- [ ] **T3.3** Refactor `POST /api/cases` (Create Case):
    - Accept `deposit_account_id` in payload.
    - Add validation: If Category Type is REVENUE/ASSET, `deposit_account_id` is required.
- [ ] **T3.4** Refactor `POST /api/cases/{id}/approve` (Finance Approval):
    - Change logic: Generate **PV** Document immediately.
    - Generate Doc No format `PV-YYMM-XXXX`.
    - Update status to `APPROVED`.
- [ ] **T3.5** Implement Receipt Upload Logic:
    - Update Attachment Upload API to set `cases.is_receipt_uploaded = True` automatically when type='RECEIPT'.
    - OR create a specific endpoint `POST /cases/{id}/confirm-receipt` if manual confirmation is preferred.
- [ ] **T3.6** Create JV API (`POST /api/documents/jv`):
    - Input: List of `case_ids` to be linked.
    - Logic: Sum amounts, create JV Document, create `jv_line_items`, and close related cases.

### Frontend Alignment (Requirements)
- [ ] **T3.7** Update `Form.tsx`: Add "Deposit Account" dropdown (Filter categories where type=ASSET) when creating Revenue/Return forms.
- [ ] **T3.8** Update Dashboard: Display PV Numbers instead of old document types.