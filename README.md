# PulseOps-Engine

PulseOps-Engine is a backend service designed to manage student enrollment pipelines, automate record provisioning, and synchronize data between GoHighLevel (GHL) and ClickUp.

## Latest Change

The latest change adds an independent outbox publisher so pending database events continue retrying without waiting for another webhook. The publisher runs as a dedicated Docker Compose service, polls every five seconds, and handles up to 50 due events per batch while skipping rows locked by other publishers. Failed deliveries remain durable and use capped exponential retry delays; the publisher also closes its queue client on graceful shutdown.

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
- **Readiness Monitoring**: Separate liveness and readiness endpoints let container orchestrators restart unhealthy processes while keeping traffic away from instances that cannot reach PostgreSQL.
- **Compose Readiness Integration**: Docker Compose probes `/ready` with the Python runtime already included in the image, so container health tracks database-backed availability without relying on an undeclared `curl` package.
- **Deployment Validation**: CI verifies the Alembic migration graph and parses the Docker Compose configuration before changes can merge.
- **Strict Financial Webhook Idempotency**: Payment and offboarding webhooks require the provider's stable event ID instead of inventing a random fallback that would make retries impossible to deduplicate.
- **Auditable Offboarding Transitions**: Offboarding records both entry into `offboarding` and the final `refunded` or `cancelled` state, correlating both history entries to the provider event ID.
- **Normalized Payment States**: Payment webhook statuses are trimmed, lowercased, and checked against an explicit allowlist before persistence or outbox publication.
- **Database Payment Invariants**: Migration `0007` mirrors payment status validation in PostgreSQL, rejects negative amounts and lowercase currency codes, and indexes payment status/time queries.
- **Canonical Payment Currencies**: Payment webhooks trim and uppercase three-letter currency codes, rejecting malformed values before database access.
- **Currency Validation Coverage**: Regression tests verify normalization of padded lowercase currency values and rejection of malformed currency codes.
- **Recovery Queue Contract**: The provisioning worker and recovery script share a strict message schema containing the positive student `id`, preventing incompatible recovery messages from being silently discarded.
- **Conservative Reconciliation**: Reconciliation is read-only unless `--fix` is specified; it only requeues eligible students after ClickUp confirms the referenced task is missing with HTTP 404. It locks and revalidates the current status and task reference before repair, and writes the student update and retry intent transactionally through the outbox. Missing task references and ClickUp authorization, rate-limit, server, or network errors are reported without changing student state.
- **Independent Outbox Dispatch**: A dedicated publisher polls PostgreSQL for due outbox events and retries Azure Queue delivery independently of webhook traffic; Docker Compose runs it as a separate restartable service.

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
- `src/api/webhooks.py`: Provides `/health` liveness and `/ready` database-readiness probes.
- `src/services/`: External API clients (ClickUp, Queue Service) and business logic.
- `src/services/outbox_service.py`: Retryable publisher for pending PostgreSQL outbox events.
- `src/tasks/`: Logic for data processing and orchestration.
- `src/workers/`: Provisioning and independent outbox publisher loops with queue retries and graceful shutdown.
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
   This applies revisions `0001` through `0007`, including lifecycle history, schema-hardening constraints, durable messaging, payment/offboarding workflows, and payment invariants.

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

Validate the deployment graph locally with the same checks used by CI:

```bash
alembic heads
alembic history
docker compose config --quiet
```

The migration output should show one head at `0007`; Compose configuration requires
the CI-safe values from `.env.example` or an equivalent `.env` file.

- **Lifecycle migration**: Apply revision `0003` with `alembic upgrade head` to create the `student_transitions` audit table.
- **Schema hardening migration**: Revision `0004` adds cohort data, operational indexes, and database constraints for the student record.
- **Messaging migration**: Revision `0005` adds inbox deduplication and retryable outbox records.
- **Operations migration**: Revision `0006` adds payment-event and offboarding-case records.
- **Payment hardening migration**: Revision `0007` adds database checks for supported statuses, non-negative amounts, uppercase currencies, and an operational status/time index.
- **Payment webhook**: `POST /webhooks/payments/updated` validates the provider signature, records the payment independently, escalates failed or past-due payments to `at_risk`, and returns an idempotent duplicate response for retried events.
- **Offboarding webhook**: `POST /webhooks/offboarding` accepts signed `refund` or `cancel` actions, transitions the student to `refunded` or `cancelled`, persists the reason and case state, and emits a durable offboarding command.
- **Financial event IDs**: Payment and offboarding requests must include `X-Webhook-Event-Id`; missing identifiers return HTTP 400 before any database mutation.
- **Payment status validation**: Supported statuses are `pending`, `processing`, `succeeded`, `paid`, `failed`, `past_due`, `declined`, `refunded`, and `cancelled`; unsupported values are rejected before database access.
- **Payment status normalization**: Values are trimmed and lowercased before validation, so provider casing or surrounding whitespace cannot create inconsistent stored states or outbox event names.
- **Offboarding audit history**: Each accepted offboarding event records the intermediate and terminal lifecycle transitions with the same provider-event correlation ID.
- **CSM assignment**: Set `CSM_IDS=csm-a,csm-b` to enable least-loaded assignment for new GHL onboarding records; leave it unset to preserve unassigned intake behavior.
- **Alert delivery**: Set `ALERT_WEBHOOK_URL` for general alerts, or override with `CSM_ALERT_WEBHOOK_URL` and `ENG_ALERT_WEBHOOK_URL`; delivery failures are logged and raised for scheduler retry handling.
- **Alert payloads**: Notifications use a provider-neutral `text` field plus a structured `details` object, allowing chat destinations and downstream automation to consume the same event context.
- **Health probes**: `GET /health` checks process liveness only; `GET /ready` performs a PostgreSQL round trip and returns HTTP 503 when the database is unavailable.
- **Compose healthcheck**: The web container calls `/ready` with Python's standard-library HTTP client; this keeps the image dependency set and deployment health contract aligned.
- **CI deployment checks**: GitHub Actions confirms revision `0007` is the current migration head and runs `docker compose config --quiet` with safe CI-only environment values.
- **Migration graph**: The initial migration is revision `0001`, followed linearly through `0007`; CI fails if a revision reference is missing or multiple heads are introduced.
- **Outbox operation**: Webhooks commit the student update and outbox command together; the publisher then retries pending commands with exponential backoff until Azure Queue accepts them.
- **Outbox publisher service**: Docker Compose runs `src/workers/outbox_publisher.py` as an independent process, polling every five seconds so retryable outbox events do not depend on later API requests.
- **Dead-letter operation**: Messages that exceed the worker dequeue-attempt limit are copied to `student-provisioning-deadletter` for inspection and replay instead of being silently discarded.
- **Lifecycle behavior**: Invalid status changes are rejected, while supported ClickUp statuses are normalized into internal lifecycle states before persistence.
- **Webhooks**: Use the `scripts/simulate_*.py` scripts to test incoming webhook payloads.
- **Seeding**: Use `scripts/seed_clickup_students.py` to populate the database with initial data.
- **Worker**: Run the worker manually for testing using `scripts/run_worker.py`.
- **Outbox publisher**: Run `python src/workers/outbox_publisher.py` to independently poll and publish pending outbox events; Docker Compose starts this process as `outbox-publisher`.
- **Worker compatibility**: `src/tasks/processor.py` delegates to the canonical provisioning worker so there is one queue-processing implementation.
- **SLA Auditor**: Run the periodic operational audit script to check ClickUp sync and SLA breaches using `scripts/run_sla_auditor.py`.
- **Recovery**: Re-enqueue pending or queued students without a ClickUp task using `scripts/requeue_pending_students.py`. Recovery messages use the shared `{"id": <student_id>}` contract consumed by the provisioning worker.
- **Reconciliation**: Run `python scripts/reconcile_students.py` for a read-only review of stale active records. Add `--fix` to clear a task reference and stage a retry only when ClickUp explicitly returns 404; other provider/network errors and records without a task reference are never treated as proof that a task is missing.

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
5. Refund and cancellation events create an `offboarding_cases` record, persist both lifecycle transitions with a shared correlation ID, and enqueue a durable command for access revocation and final communication workflows.
6. Operators can reconstruct the workflow as `current status → offboarding → refunded/cancelled` from `student_transitions` without relying only on the student's final status.

Payment integrations should send one of the documented statuses in any casing;
the API stores the normalized lowercase value and rejects unknown values before
opening a database transaction.

Financial providers must send a stable `X-Webhook-Event-Id` header. The API rejects
requests without it so a network retry cannot create a second financial record or
repeat an offboarding transition under a newly generated identifier.

Example request headers for either financial endpoint:

```http
X-Webhook-Signature: sha256=<HMAC-SHA256-of-raw-request-body>
X-Webhook-Event-Id: payment-event-2026-0001
Content-Type: application/json
```

The event ID must remain unchanged when the provider retries the same raw payload;
changing it intentionally represents a new provider event.

The `student_transitions` records use that same event ID as `correlation_id`,
linking the intermediate `offboarding` entry and terminal outcome to the original
provider notification.

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

### Health and readiness flow

1. The liveness probe calls `GET /health` to verify that the FastAPI process can serve requests.
2. The readiness probe calls `GET /ready`, which executes `SELECT 1` through the application's async SQLAlchemy session factory.
3. A successful dependency check returns `200` with database status metadata.
4. A database connection failure returns `503`, allowing Docker, Azure, or another orchestrator to stop routing traffic until recovery.

Check both endpoints locally after starting Docker Compose:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Use `/health` for container liveness/restart checks and `/ready` for load-balancer or deployment traffic gating.
Docker Compose uses the same readiness contract for the web container:

```bash
docker compose ps
docker inspect --format="{{json .State.Health}}" pulseops-engine-web-1
```

The container is healthy only when the Python-based check can receive a successful response from `/ready`; `/health` remains available for process-only diagnostics.
