# PulseOps-Engine

PulseOps-Engine is a backend service designed to manage student enrollment pipelines, automate record provisioning, and synchronize data between GoHighLevel (GHL) and ClickUp.

## Features

- **Webhook Handling**: Receives and validates webhooks from GoHighLevel (e.g., "Deal Won") and ClickUp (Task Updates).
- **Resilient Azure Integration**: Implemented automatic retries and exponential backoff for Azure Storage Queue operations to handle network disconnects and transient errors.
- **Heartbeat Monitoring**: Added worker health tracking with periodic heartbeat logging to ensure continuous processing.
- **Graceful Shutdown**: Implemented signal handling (SIGINT/SIGTERM) for clean worker termination without interrupting in-flight tasks.
- **Fault Tolerance**: Added top-level crash logging, non-zero exit codes, and a failure threshold with automated alert dispatching for the provisioning worker.
- **SLA & CSM Monitoring**: Implemented an auditing engine for real-time SLA tracking, CSM attribution, and contextual alert routing to separate infrastructure failures from business process breaches.
- **Canonical Provisioning Worker**: The provisioning worker now owns queue consumption, atomically claims pending students, handles transient database lock conflicts, supports graceful SIGINT/SIGTERM shutdown, and closes Azure Queue resources cleanly.
- **Regression Coverage**: Added unit tests for the Student ORM model, SLA evaluation, and webhook signature validation.
- **Continuous Integration**: GitHub Actions compiles the Python sources and runs the unit test suite on pushes to `main` and pull requests.
- **Explicit Lifecycle Contracts**: Student status transitions are validated through a typed state machine, recorded in `student_transitions`, and represented by stable domain-event envelopes.
- **Scale-Oriented Student Schema**: Cohort is persisted for segmentation, dashboard query indexes cover status/CSM/program workloads, and database checks protect health scores, follow-up counts, lifecycle statuses, and duplicate ClickUp task IDs.
- **Durable Messaging**: Inbox deduplication prevents repeated provider events, PostgreSQL outbox records close the database-to-queue delivery gap, retry backoff preserves failed publications, and exhausted queue messages are sent to `student-provisioning-deadletter`.
- **Payment and Offboarding Workflows**: Payment events are stored independently from student status, failed payments can mark a student at risk, and refund/cancellation events create auditable offboarding cases with durable workflow commands.
- **Payment Idempotency**: Payment webhooks deduplicate both provider event IDs and provider payment IDs, preventing retries from creating duplicate payment records or repeated student transitions.
- **Refund and Cancellation Handling**: Signed refund or cancellation webhooks move eligible students through the lifecycle state machine, create an open offboarding case, and enqueue follow-up work through the transactional outbox.
- **Workload-Aware CSM Assignment**: New onboarding records can be assigned to the least-loaded configured CSM using active student counts, with deterministic tie-breaking for predictable operations.
- **Operational Alert Delivery**: Configured alert webhooks now receive structured engineering and CSM notifications with bounded HTTP timeouts and explicit delivery failures.

## Tech Stack

- **Framework**: FastAPI
- **Language**: Python 3.11+
- **Database**: PostgreSQL/SQLite (via SQLAlchemy)
- **Migrations**: Alembic
- **Task Scheduling**: Custom background worker implementation
- **Infrastructure**: Docker & Docker Compose for deployment
- **Testing**: Python `unittest` with GitHub Actions CI

## Project Structure

- `ARCHITECTURE.md`: High-level system architecture and component breakdown.
- `src/api/`: API routes and webhook endpoints.
- `src/core/`: Configuration, database setup, and core logic.
- `src/domain/`: Typed lifecycle states, transition rules, and domain-event contracts.
- `src/models/`: Database models (e.g., Student).
- `src/models/student_transition.py`: Durable audit history for student lifecycle changes.
- `src/models/messaging.py`: Inbox and outbox persistence models for reliable event delivery.
- `src/models/student_operations.py`: Payment-event and offboarding-case persistence models.
- `src/services/csm_allocator.py`: Workload-aware CSM selection based on active assigned students.
- `src/services/alert_service.py`: Shared structured webhook delivery for operational and CSM alerts.
- `src/services/`: External API clients (ClickUp, Queue Service) and business logic.
- `src/services/outbox_service.py`: Retryable publisher for pending PostgreSQL outbox events.
- `src/tasks/`: Logic for data processing and orchestration.
- `src/workers/`: Canonical background worker execution loop with queue retries and graceful shutdown.
- `migrations/`: Alembic migration scripts.
- `scripts/`: Utility scripts for seeding data and simulating webhook traffic.
- `tests/`: Regression tests for core model, webhook, and SLA behavior.
- `.github/workflows/ci.yml`: Automated compilation and test workflow.

## Student Data Model

The `students` table is the operational source of truth for onboarding and CSM workflows:

- `program_type` and `cohort` support program-level and cohort-level reporting.
- `status`, `assigned_csm_id`, and `updated_at` are indexed for queue, dashboard, and auditor queries.
- `health_score` is constrained to `0-100`, while `follow_up_count` cannot be negative.
- Lifecycle values are constrained to the supported state-machine statuses.
- `clickup_task_id` is unique so one external task cannot be attached to multiple students.
- `student_transitions` stores the immutable history of lifecycle changes.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- Access keys for ClickUp and GoHighLevel

### Installation

<!-- The commands in this section are operational steps: install the dependency
     set, provide environment-specific secrets, then bring the schema and service up. -->

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd pulseops-engine
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Environment Setup:
   Copy the example environment file and update with your secrets:
   ```bash
   cp .env.example .env
   ```
   To enable workload-aware CSM assignment for new onboarding records, add a
   comma-separated owner pool to `.env`:
   ```dotenv
   CSM_IDS=csm-a,csm-b,csm-c
   ```
   If `CSM_IDS` is omitted, intake remains unassigned for manual routing.

4. Database Migrations:
   <!-- Applying migrations creates or updates tables to the revision expected by the
        running application; run it against the intended database before startup. -->
   Ensure the database is up and run migrations:
   ```bash
   alembic upgrade head
   ```
   This applies revisions `0001` through `0006`, including lifecycle history, schema-hardening constraints, durable messaging, and payment/offboarding workflows.

5. Run the Application:
   <!-- Compose supplies local service wiring and starts the API with supporting
        infrastructure; --build refreshes the image after source or dependency changes. -->
   Start the service using Docker Compose:
   ```bash
   docker-compose up --build
   ```

## Development Tools

### Automated validation

Run the same checks used by CI before opening a pull request:

```bash
python -m compileall -q src migrations scripts tests
python -m unittest discover -s tests -v
```

- **Lifecycle migration**: Apply revision `0003` with `alembic upgrade head` to create the `student_transitions` audit table.
- **Schema hardening migration**: Revision `0004` adds cohort data, operational indexes, and database constraints for the student record.
- **Messaging migration**: Revision `0005` adds inbox deduplication and retryable outbox records.
- **Operations migration**: Revision `0006` adds payment-event and offboarding-case records.
- **Payment webhook**: `POST /webhooks/payments/updated` validates the provider signature, records the payment independently, escalates failed or past-due payments to `at_risk`, and returns an idempotent duplicate response for retried events.
- **Offboarding webhook**: `POST /webhooks/offboarding` accepts signed `refund` or `cancel` actions, transitions the student to `refunded` or `cancelled`, persists the reason and case state, and emits a durable offboarding command.
- **CSM assignment**: Set `CSM_IDS=csm-a,csm-b` to enable least-loaded assignment for new GHL onboarding records; leave it unset to preserve unassigned intake behavior.
- **Alert delivery**: Set `ALERT_WEBHOOK_URL` for general alerts, or override with `CSM_ALERT_WEBHOOK_URL` and `ENG_ALERT_WEBHOOK_URL`; delivery failures are logged and raised for scheduler retry handling.
- **Alert payloads**: Notifications use a provider-neutral `text` field plus a structured `details` object, allowing chat destinations and downstream automation to consume the same event context.
- **Outbox operation**: Webhooks commit the student update and outbox command together; the publisher then retries pending commands with exponential backoff until Azure Queue accepts them.
- **Dead-letter operation**: Messages that exceed the worker dequeue-attempt limit are copied to `student-provisioning-deadletter` for inspection and replay instead of being silently discarded.
- **Lifecycle behavior**: Invalid status changes are rejected, while supported ClickUp statuses are normalized into internal lifecycle states before persistence.
- **Webhooks**: Use the `scripts/simulate_*.py` scripts to test incoming webhook payloads.
- **Seeding**: Use `scripts/seed_clickup_students.py` to populate the database with initial data.
- **Worker**: Run the worker manually for testing using `scripts/run_worker.py`.
- **Worker compatibility**: `src/tasks/processor.py` delegates to the canonical provisioning worker so there is one queue-processing implementation.
- **SLA Auditor**: Run the periodic operational audit script to check ClickUp sync and SLA breaches using `scripts/run_sla_auditor.py`.
- **Recovery**: Re-enqueue unprovisioned or failed student records using `scripts/requeue_pending_students.py`.
- **Reconciliation**: Reconcile stale database records with ClickUp tasks using `scripts/reconcile_students.py`.

### Reliable event flow

1. A signed provider webhook is validated and assigned an event ID.
2. The inbox table rejects a previously processed provider event.
3. The student state change and an outbox command are committed in one PostgreSQL transaction.
4. The outbox publisher sends the command to Azure Storage Queue and records publication or retry metadata.
5. The worker claims the student, performs provisioning, and acknowledges the queue message.
6. Repeatedly failing messages are moved to the dead-letter queue for operator review.

### Payment and offboarding flow

1. The payment provider sends a signed payment update with a provider event ID and payment ID.
2. The API rejects invalid signatures and treats either previously processed identifier as an idempotent duplicate.
3. The payment record is committed separately from the student aggregate so financial history remains auditable.
4. Failed, past-due, or declined payments request an `at_risk` lifecycle transition; invalid transitions return a conflict rather than silently changing state.
5. Refund and cancellation events create an `offboarding_cases` record, transition the student through `offboarding`, and enqueue a durable command for access revocation and final communication workflows.

### Workload-aware assignment flow

1. Configure eligible owners with the comma-separated `CSM_IDS` environment variable.
2. During a new GHL onboarding transaction, count each configured CSM's active assigned students.
3. Assign the student to the lowest workload; use the identifier as a stable tie-breaker when counts match.
4. Exclude terminal records from the count so completed, refunded, and cancelled work does not distort current capacity.

### Operational alert flow

1. A worker or scheduled auditor calls the shared alert service with a subject, message, and optional details.
2. The service selects the specific channel override when configured, otherwise it uses `ALERT_WEBHOOK_URL`.
3. The webhook request uses a five-second timeout so a slow notification provider cannot hang the event loop indefinitely.
4. Non-success HTTP responses are logged and raised, allowing the surrounding scheduler or worker policy to retry or surface the failure.
