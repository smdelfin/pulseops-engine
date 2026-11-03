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
- `src/models/`: Database models (e.g., Student).
- `src/services/`: External API clients (ClickUp, Queue Service) and business logic.
- `src/tasks/`: Logic for data processing and orchestration.
- `src/workers/`: Canonical background worker execution loop with queue retries and graceful shutdown.
- `migrations/`: Alembic migration scripts.
- `scripts/`: Utility scripts for seeding data and simulating webhook traffic.
- `tests/`: Regression tests for core model, webhook, and SLA behavior.
- `.github/workflows/ci.yml`: Automated compilation and test workflow.

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

4. Database Migrations:
   <!-- Applying migrations creates or updates tables to the revision expected by the
        running application; run it against the intended database before startup. -->
   Ensure the database is up and run migrations:
   ```bash
   alembic upgrade head
   ```

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

- **Webhooks**: Use the `scripts/simulate_*.py` scripts to test incoming webhook payloads.
- **Seeding**: Use `scripts/seed_clickup_students.py` to populate the database with initial data.
- **Worker**: Run the worker manually for testing using `scripts/run_worker.py`.
- **Worker compatibility**: `src/tasks/processor.py` delegates to the canonical provisioning worker so there is one queue-processing implementation.
- **SLA Auditor**: Run the periodic operational audit script to check ClickUp sync and SLA breaches using `scripts/run_sla_auditor.py`.
- **Recovery**: Re-enqueue unprovisioned or failed student records using `scripts/requeue_pending_students.py`.
- **Reconciliation**: Reconcile stale database records with ClickUp tasks using `scripts/reconcile_students.py`.
