# - Imports hashing and HMAC primitives used to construct valid webhook signatures in tests.
# - Architectural Purpose: Exercises the same standard-library cryptography used at the API boundary.
# - Plain-English: 'Create realistic signed test requests without contacting a provider.'
import hashlib
import hmac
# - Imports environment access to configure required settings before application imports.
# - Architectural Purpose: Settings are instantiated at import time, so test configuration must come first.
# - Plain-English: 'Set up the test process environment before loading the app.'
import os
# - Imports unittest's test-case and assertion framework.
# - Architectural Purpose: Keeps regression tests runnable with Python's built-in test discovery.
# - Plain-English: 'Use Python's standard test runner.'
import unittest
# - Imports path handling for reading repository configuration in tests.
# - Architectural Purpose: Locates project files independent of the current working directory.
# - Plain-English: 'Build reliable paths to files that tests inspect.'
from pathlib import Path


# - Supplies a local async database URL only when the caller has not already configured one.
# - Architectural Purpose: Allows safe module import without replacing an explicit test or deployment setting.
# - Plain-English: 'Provide a harmless database setting for tests that do not connect.'
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/pulseops")
# - Supplies an emulator connection string for configuration initialization.
# - Architectural Purpose: Avoids requiring a live Azure Storage account during unit tests.
# - Plain-English: 'Use the local storage emulator setting for tests.'
os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
# - Provides a placeholder ClickUp token required by settings validation.
# - Architectural Purpose: Tests use fake credentials and never call external services.
# - Plain-English: 'Satisfy configuration with a test-only API token.'
os.environ.setdefault("CLICKUP_API_TOKEN", "test-token")
# - Provides a placeholder ClickUp list identifier for application startup.
# - Architectural Purpose: Prevents tests from depending on a real ClickUp workspace.
# - Plain-English: 'Use a fake list for configuration.'
os.environ.setdefault("CLICKUP_DEFAULT_LIST_ID", "test-list")
# - Provides a known signing secret for webhook signature tests.
# - Architectural Purpose: Lets tests create deterministic valid and invalid HMAC values.
# - Plain-English: 'Use a test-only secret to verify signature behavior.'
os.environ.setdefault("GHL_WEBHOOK_SECRET", "ghl-secret")
# - Provides the corresponding ClickUp signing secret during app import.
# - Architectural Purpose: Ensures application settings can initialize without production credentials.
# - Plain-English: 'Use a fake ClickUp secret for test startup.'
os.environ.setdefault("CLICKUP_WEBHOOK_SECRET", "clickup-secret")

# - Imports API schemas, webhook helpers, and the FastAPI app after required environment setup.
# - Architectural Purpose: Exercises boundary validation and route metadata without starting a server.
# - Plain-English: 'Load the actual API components the tests verify.'
from src.api.webhooks import PaymentWebhook, _require_event_id, _verify_signature, app
from src.domain.provisioning import parse_provisioning_message, serialize_provisioning_message
from scripts.reconcile_students import classify_clickup_error
from src.services.clickup_client import ClickUpAPIError, ClickUpNotFoundError, ClickUpTimeoutError
# - Imports the core ORM model for schema and auditor test cases.
# - Architectural Purpose: Verifies the production model mapping rather than a test duplicate.
# - Plain-English: 'Test the real student database model.'
from src.models.student import Student
# - Imports operational SLA evaluation logic.
# - Architectural Purpose: Protects the business alert behavior from regressions.
# - Plain-English: 'Check the real student monitoring rules.'
from src.services.student_auditor import StudentAuditor
# - Imports workload-based CSM selection behavior.
# - Architectural Purpose: Verifies deterministic assignment without a database or network.
# - Plain-English: 'Test how the system chooses a CSM.'
from src.services.csm_allocator import CSMAllocator
# - Imports the provider-neutral alert payload builder.
# - Architectural Purpose: Tests notification structure independently of HTTP delivery.
# - Plain-English: 'Check what information an alert contains.'
from src.services.alert_service import build_alert_payload
# - Imports lifecycle domain rules and event contracts.
# - Architectural Purpose: Ensures status decisions are tested at the domain boundary.
# - Plain-English: 'Test the shared lifecycle definitions and transitions.'
from src.domain.lifecycle import InvalidStudentTransition, StudentDomainEvent, StudentStatus, transition_status
# - Imports durable inbox/outbox models for schema contract assertions.
# - Architectural Purpose: Protects database-backed messaging guarantees.
# - Plain-English: 'Check the tables that make message delivery reliable.'
from src.models.messaging import InboxEvent, OutboxEvent
# - Imports payment and offboarding models for financial integrity assertions.
# - Architectural Purpose: Verifies persistence constraints remain aligned with workflow behavior.
# - Plain-English: 'Check the real payment and departure records.'
from src.models.student_operations import OffboardingCase, PaymentEvent
# - Imports FastAPI's HTTP exception for asserting boundary error codes.
# - Architectural Purpose: Tests public request behavior without running an ASGI server.
# - Plain-English: 'Check the status code produced by invalid requests.'
from fastapi import HTTPException
# - Imports a minimal ASGI request object for helper tests.
# - Architectural Purpose: Exercises header parsing without constructing a network request.
# - Plain-English: 'Create a small in-memory request for tests.'
from starlette.requests import Request


# - Groups related behavior checks into unittest-discoverable test methods.
# - Architectural Purpose: Keeps regression checks runnable in CI with no external service dependencies.
# - Plain-English: 'Collect the project's core behavior checks.'
class CoreBehaviorTests(unittest.TestCase):
    # Ensure recovery serializes the same id field and the worker accepts it.
    def test_recovery_messages_match_worker_queue_contract(self):
        recovery_message = serialize_provisioning_message(23)
        worker_payload = parse_provisioning_message(recovery_message)
        self.assertEqual(worker_payload.id, 23)
        with self.assertRaises(ValueError):
            parse_provisioning_message('{"student_id": 23}')

    # Ensure a provider failure is not misclassified as proof of a missing task.
    def test_reconciliation_only_treats_clickup_404_as_confirmed_missing(self):
        self.assertEqual(
            classify_clickup_error(ClickUpNotFoundError("missing", status_code=404)),
            "CONFIRMED_MISSING_IN_CLICKUP",
        )
        self.assertEqual(
            classify_clickup_error(ClickUpAPIError("unauthorized", status_code=401)),
            "CLICKUP_HTTP_ERROR_401",
        )
        self.assertEqual(
            classify_clickup_error(ClickUpAPIError("server error", status_code=500)),
            "CLICKUP_HTTP_ERROR_500",
        )
        self.assertEqual(
            classify_clickup_error(ClickUpTimeoutError("timeout")),
            "CLICKUP_UNAVAILABLE",
        )

    # - Verifies that the state machine blocks a transition not present in its allowlist.
    # - Architectural Purpose: Prevents invalid business states from being persisted by any caller.
    # - Plain-English: 'Prove that a completed student cannot jump back into queue processing.'
    def test_lifecycle_rejects_invalid_transition(self):
        # - Expects the domain layer to raise its explicit transition exception.
        with self.assertRaises(InvalidStudentTransition):
            # - Requests the intentionally forbidden transition.
            transition_status(StudentStatus.COMPLETED, StudentStatus.QUEUED)

    # - Verifies the event envelope retains stable aggregate and type fields.
    # - Architectural Purpose: Protects the outbox/consumer contract from accidental schema drift.
    # - Plain-English: 'Check that a student event identifies what happened and to whom.'
    def test_domain_event_has_stable_envelope(self):
        # - Creates a domain event with a minimal payload for serialization testing.
        event = StudentDomainEvent("student.queued", 7, {"source": "test"})
        # - Confirms serialization preserves the aggregate identity.
        self.assertEqual(event.as_dict()["aggregate_id"], 7)
        # - Confirms serialization preserves the event category.
        self.assertEqual(event.as_dict()["event_type"], "student.queued")

    # - Verifies the Student ORM table includes the operational pause flag.
    # - Architectural Purpose: Prevents model changes from dropping the pause-control field.
    # - Plain-English: 'Check that a student can be paused in the database model.'
    def test_student_model_contains_pause_flag(self):
        # - Checks that the mapped table defines the named column.
        self.assertIn("is_paused", Student.__table__.columns)
        # - Ensures every row has an explicit pause value rather than an ambiguous null.
        self.assertFalse(Student.__table__.c.is_paused.nullable)

    # - Verifies reporting dimensions and lookup indexes remain part of the student schema.
    # - Architectural Purpose: Protects query paths used by dashboards, assignment, and ClickUp sync.
    # - Plain-English: 'Check that reporting fields and useful database indexes exist.'
    def test_student_model_contains_dashboard_dimensions_and_indexes(self):
        # - Confirms cohort segmentation remains available on the mapped table.
        self.assertIn("cohort", Student.__table__.columns)
        # - Collects mapped index names for focused assertions.
        index_names = {index.name for index in Student.__table__.indexes}
        # - Checks operational queue lookup by status and recent update time.
        self.assertIn("ix_students_status_updated_at", index_names)
        # - Checks reporting lookup by program, cohort, and lifecycle state.
        self.assertIn("ix_students_program_cohort_status", index_names)
        # - Checks that external ClickUp task IDs remain uniquely indexed.
        self.assertIn("ux_students_clickup_task_id", index_names)

    # - Verifies inbox/outbox tables retain fields needed for durable delivery.
    # - Architectural Purpose: Ensures event IDs, payloads, scheduling, and retries remain representable.
    # - Plain-English: 'Check that the message system can remember and retry its work.'
    def test_messaging_models_define_durable_delivery_fields(self):
        # - Confirms inbox records can identify a provider event for deduplication.
        self.assertIn("provider_event_id", InboxEvent.__table__.columns)
        # - Confirms outgoing records retain the serialized event body.
        self.assertIn("payload", OutboxEvent.__table__.columns)
        # - Confirms outgoing records can be scheduled for a future retry.
        self.assertIn("available_at", OutboxEvent.__table__.columns)
        # - Confirms each publication attempt can be counted.
        self.assertIn("attempts", OutboxEvent.__table__.columns)

    # - Verifies money and departure workflows have separate persistence models.
    # - Architectural Purpose: Prevents financial history and offboarding tasks from collapsing into student status alone.
    # - Plain-English: 'Check that payment facts and departure checklists have their own fields.'
    def test_payment_and_offboarding_models_are_separate_workflows(self):
        # - Confirms payment events can be deduplicated against the provider's payment identifier.
        self.assertIn("provider_payment_id", PaymentEvent.__table__.columns)
        # - Confirms provider failure details remain available for support.
        self.assertIn("failure_reason", PaymentEvent.__table__.columns)
        # - Confirms offboarding can track access revocation completion.
        self.assertIn("access_revoked", OffboardingCase.__table__.columns)
        # - Confirms offboarding can track whether final communication was sent.
        self.assertIn("final_communication_sent", OffboardingCase.__table__.columns)

    # - Verifies PostgreSQL-level checks and indexes are mirrored in ORM metadata.
    # - Architectural Purpose: Keeps app schema declarations and migration expectations aligned.
    # - Plain-English: 'Check that invalid payment values are blocked and common queries are indexed.'
    def test_payment_model_enforces_database_invariants(self):
        # - Extracts constraint names for concise contract checks.
        constraint_names = {constraint.name for constraint in PaymentEvent.__table__.constraints}
        # - Extracts index names declared on the table.
        index_names = {index.name for index in PaymentEvent.__table__.indexes}
        # - Ensures the database restricts statuses to the supported set.
        self.assertIn("ck_payment_events_status", constraint_names)
        # - Ensures the database rejects negative amounts.
        self.assertIn("ck_payment_events_amount", constraint_names)
        # - Ensures supplied currency codes use canonical uppercase.
        self.assertIn("ck_payment_events_currency_upper", constraint_names)
        # - Ensures status and occurrence time have a supporting composite index.
        self.assertIn("ix_payment_events_status_occurred_at", index_names)

    # - Verifies the auditor flags a student that exceeds the processing SLA.
    # - Architectural Purpose: Protects operational alert decisions from regressions.
    # - Plain-English: 'Check that a student stuck in processing is identified for attention.'
    def test_auditor_flags_status_sla_breach(self):
        # - Constructs a minimal mapped student with a status evaluated by the auditor.
        student = Student(
            id=1,
            name="Test Student",
            ghl_contact_id="ghl-1",
            status="processing",
            program_type="FastTrack",
        )
        # - Runs the same evaluation used by operational auditing.
        result = StudentAuditor().evaluate_student(student)
        # - Confirms the evaluator reports the expected breach category.
        self.assertEqual(result["breach_type"], "STATUS_SLA")

    # - Verifies CSM allocation selects the least-loaded person and resolves ties consistently.
    # - Architectural Purpose: Makes assignment predictable and avoids random workload imbalance.
    # - Plain-English: 'Check that new work goes to the least busy CSM.'
    def test_csm_allocator_prefers_least_loaded_and_breaks_ties(self):
        # - Supplies a clear workload difference and checks the lower-load CSM is selected.
        selected = CSMAllocator.choose_least_loaded(
            ["csm-b", "csm-a"],
            {"csm-a": 2, "csm-b": 1},
        )
        # - Confirms the lower active-student count wins.
        self.assertEqual(selected, "csm-b")
        # - Confirms equal workloads use stable identifier ordering.
        self.assertEqual(
            CSMAllocator.choose_least_loaded(["csm-b", "csm-a"], {}),
            "csm-a",
        )

    # - Verifies the alert builder preserves both human-readable text and structured context.
    # - Architectural Purpose: Allows a notification destination and automation consumer to share one payload.
    # - Plain-English: 'Check that alerts include a readable message and machine-readable details.'
    def test_alert_payload_preserves_context(self):
        # - Builds a payload without performing network delivery.
        payload = build_alert_payload("Subject", "Message", {"count": 2})
        # - Checks the rendered headline and message.
        self.assertEqual(payload["text"], "*Subject*\nMessage")
        # - Checks that structured metadata survives unchanged.
        self.assertEqual(payload["details"]["count"], 2)

    # - Verifies the API exposes independent process liveness and database readiness endpoints.
    # - Architectural Purpose: Lets orchestrators restart dead processes while withholding traffic from DB-disconnected instances.
    # - Plain-English: 'Check that health and readiness are separate routes.'
    def test_application_exposes_separate_liveness_and_readiness_probes(self):
        # - Builds a set of registered route paths for fast membership checks.
        routes = {route.path for route in app.routes}
        # - Confirms the process-only liveness endpoint exists.
        self.assertIn("/health", routes)
        # - Confirms the database-backed readiness endpoint exists.
        self.assertIn("/ready", routes)

    # - Verifies Compose health monitoring targets the database-aware readiness route.
    # - Architectural Purpose: Aligns container health with the traffic-serving dependency contract.
    # - Plain-English: 'Check the container waits for the app's database check, not just process startup.'
    def test_compose_healthcheck_uses_readiness_probe(self):
        # - Resolves the repository Compose file relative to this test module.
        compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text()
        # - Requires the configured readiness endpoint.
        self.assertIn("http://localhost:8000/ready", compose)
        # - Rejects an obsolete liveness-only probe configuration.
        self.assertNotIn("curl -f http://localhost:8000/health", compose)

    # - Verifies CI continues to validate both migration topology and Compose configuration.
    # - Architectural Purpose: Prevents schema/deployment configuration errors from reaching merge.
    # - Plain-English: 'Check that the automated workflow still checks migrations and Docker wiring.'
    def test_ci_validates_migrations_and_compose_configuration(self):
        # - Reads the workflow from a path rooted at the repository, not the current shell directory.
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text()
        # - Confirms migration graph validation remains configured.
        self.assertIn("Validate migration graph", workflow)
        # - Confirms Compose parsing remains configured.
        self.assertIn("Validate Docker Compose configuration", workflow)
        # - Confirms CI checks the rendered Compose model without starting containers.
        self.assertIn("docker compose config --quiet", workflow)

    # - Verifies a valid SHA-256 HMAC signature is accepted by the webhook helper.
    # - Architectural Purpose: Protects authenticated webhook intake from accidental signature logic changes.
    # - Plain-English: 'Check that a correctly signed provider message passes.'
    def test_webhook_signature_accepts_valid_digest(self):
        # - Defines exact request bytes so the computed signature matches the payload.
        body = b'{"name":"Test Student"}'
        # - Uses a deterministic secret that is safe for local tests.
        secret = "secret"
        # - Computes the provider-compatible HMAC-SHA256 digest.
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        # - Confirms verification completes without raising an HTTP error.
        self.assertIsNone(_verify_signature(body, f"sha256={signature}", secret))

    # - Verifies an invalid HMAC is rejected with an authentication response.
    # - Architectural Purpose: Ensures untrusted webhook payloads cannot reach business processing.
    # - Plain-English: 'Check that a bad signature is denied.'
    def test_webhook_signature_rejects_invalid_digest(self):
        # - Captures the expected API exception raised for a mismatched signature.
        with self.assertRaises(HTTPException) as raised:
            # - Supplies a deliberately invalid digest.
            _verify_signature(b"body", "sha256=invalid", "secret")
        # - Confirms the public response identifies an authentication failure.
        self.assertEqual(raised.exception.status_code, 401)

    # - Verifies financial webhook event IDs are mandatory and read from the canonical request header.
    # - Architectural Purpose: Stable IDs are the foundation for safe provider retry deduplication.
    # - Plain-English: 'Check that financial events have a stable identity.'
    def test_financial_webhooks_require_stable_event_ids(self):
        # - Constructs a request with no headers to simulate a missing provider event identifier.
        missing_id = Request({"type": "http", "headers": []})
        # - Expects the helper to reject a missing identifier.
        with self.assertRaises(HTTPException) as raised:
            _require_event_id(missing_id)
        # - Confirms the rejection is reported as a client request error.
        self.assertEqual(raised.exception.status_code, 400)

        # - Constructs a request containing a provider-generated stable event ID.
        with_id = Request({
            "type": "http",
            "headers": [(b"x-webhook-event-id", b"provider-event-1")],
        })
        # - Confirms the helper returns the exact ID used for inbox deduplication.
        self.assertEqual(_require_event_id(with_id), "provider-event-1")

    # - Verifies a supported offboarding path records both workflow stages.
    # - Architectural Purpose: Protects the explicit intermediate offboarding state from being skipped.
    # - Plain-English: 'Check that a finished student moves through offboarding before refund.'
    def test_offboarding_transition_chain_is_explicit(self):
        # - Moves a completed student into the active offboarding state.
        entered = transition_status(StudentStatus.COMPLETED, StudentStatus.OFFBOARDING)
        # - Resolves the active workflow to the refunded terminal outcome.
        finished = transition_status(entered, StudentStatus.REFUNDED)
        # - Confirms the intermediate transition result.
        self.assertEqual(entered, StudentStatus.OFFBOARDING)
        # - Confirms the final result.
        self.assertEqual(finished, StudentStatus.REFUNDED)

    # - Verifies payment status and currency are normalized while unsupported values are rejected.
    # - Architectural Purpose: Keeps webhook inputs compatible with PostgreSQL checks and reporting conventions.
    # - Plain-English: 'Check that provider casing is cleaned up and malformed financial values are refused.'
    def test_payment_statuses_are_normalized_and_whitelisted(self):
        # - Validates an input with padded uppercase status and lowercase currency.
        payload = PaymentWebhook.model_validate({
            "ghl_contact_id": "ghl-1",
            "provider": "stripe",
            "provider_payment_id": "pay-1",
            "status": " PAID ",
            "currency": " usd ",
        })
        # - Confirms status normalization removes whitespace and lowercases the enum value.
        self.assertEqual(payload.status, "paid")
        # - Confirms currency normalization trims padding and uses canonical uppercase.
        self.assertEqual(payload.currency, "USD")
        # - Expects unsupported provider statuses to fail schema validation.
        with self.assertRaises(ValueError):
            # - Supplies an unknown state that is intentionally outside the allowlist.
            PaymentWebhook.model_validate({
                "ghl_contact_id": "ghl-1",
                "provider": "stripe",
                "provider_payment_id": "pay-2",
                "status": "mystery",
            })
        # - Expects malformed currency text to fail validation before persistence.
        with self.assertRaises(ValueError):
            # - Supplies a non-alphabetic code to verify the three-letter validation rule.
            PaymentWebhook.model_validate({
                "ghl_contact_id": "ghl-1",
                "provider": "stripe",
                "provider_payment_id": "pay-3",
                "status": "paid",
                "currency": "US1",
            })


# - Runs unittest directly when this file is executed as a script.
# - Architectural Purpose: Supports both CI discovery and focused local invocation.
# - Plain-English: 'Start these tests when someone runs this file directly.'
if __name__ == "__main__":
    # - Discovers and executes test methods defined in this module.
    unittest.main()
