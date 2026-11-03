import hashlib
import hmac
import os
import unittest
from pathlib import Path


os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/pulseops")
os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
os.environ.setdefault("CLICKUP_API_TOKEN", "test-token")
os.environ.setdefault("CLICKUP_DEFAULT_LIST_ID", "test-list")
os.environ.setdefault("GHL_WEBHOOK_SECRET", "ghl-secret")
os.environ.setdefault("CLICKUP_WEBHOOK_SECRET", "clickup-secret")

from src.api.webhooks import _require_event_id, _verify_signature, app
from src.models.student import Student
from src.services.student_auditor import StudentAuditor
from src.services.csm_allocator import CSMAllocator
from src.services.alert_service import build_alert_payload
from src.domain.lifecycle import InvalidStudentTransition, StudentDomainEvent, StudentStatus, transition_status
from src.models.messaging import InboxEvent, OutboxEvent
from src.models.student_operations import OffboardingCase, PaymentEvent
from fastapi import HTTPException
from starlette.requests import Request


class CoreBehaviorTests(unittest.TestCase):
    def test_lifecycle_rejects_invalid_transition(self):
        with self.assertRaises(InvalidStudentTransition):
            transition_status(StudentStatus.COMPLETED, StudentStatus.QUEUED)

    def test_domain_event_has_stable_envelope(self):
        event = StudentDomainEvent("student.queued", 7, {"source": "test"})
        self.assertEqual(event.as_dict()["aggregate_id"], 7)
        self.assertEqual(event.as_dict()["event_type"], "student.queued")

    def test_student_model_contains_pause_flag(self):
        self.assertIn("is_paused", Student.__table__.columns)
        self.assertFalse(Student.__table__.c.is_paused.nullable)

    def test_student_model_contains_dashboard_dimensions_and_indexes(self):
        self.assertIn("cohort", Student.__table__.columns)
        index_names = {index.name for index in Student.__table__.indexes}
        self.assertIn("ix_students_status_updated_at", index_names)
        self.assertIn("ix_students_program_cohort_status", index_names)
        self.assertIn("ux_students_clickup_task_id", index_names)

    def test_messaging_models_define_durable_delivery_fields(self):
        self.assertIn("provider_event_id", InboxEvent.__table__.columns)
        self.assertIn("payload", OutboxEvent.__table__.columns)
        self.assertIn("available_at", OutboxEvent.__table__.columns)
        self.assertIn("attempts", OutboxEvent.__table__.columns)

    def test_payment_and_offboarding_models_are_separate_workflows(self):
        self.assertIn("provider_payment_id", PaymentEvent.__table__.columns)
        self.assertIn("failure_reason", PaymentEvent.__table__.columns)
        self.assertIn("access_revoked", OffboardingCase.__table__.columns)
        self.assertIn("final_communication_sent", OffboardingCase.__table__.columns)

    def test_auditor_flags_status_sla_breach(self):
        student = Student(
            id=1,
            name="Test Student",
            ghl_contact_id="ghl-1",
            status="processing",
            program_type="FastTrack",
        )
        result = StudentAuditor().evaluate_student(student)
        self.assertEqual(result["breach_type"], "STATUS_SLA")

    def test_csm_allocator_prefers_least_loaded_and_breaks_ties(self):
        selected = CSMAllocator.choose_least_loaded(
            ["csm-b", "csm-a"],
            {"csm-a": 2, "csm-b": 1},
        )
        self.assertEqual(selected, "csm-b")
        self.assertEqual(
            CSMAllocator.choose_least_loaded(["csm-b", "csm-a"], {}),
            "csm-a",
        )

    def test_alert_payload_preserves_context(self):
        payload = build_alert_payload("Subject", "Message", {"count": 2})
        self.assertEqual(payload["text"], "*Subject*\nMessage")
        self.assertEqual(payload["details"]["count"], 2)

    def test_application_exposes_separate_liveness_and_readiness_probes(self):
        routes = {route.path for route in app.routes}
        self.assertIn("/health", routes)
        self.assertIn("/ready", routes)

    def test_compose_healthcheck_uses_readiness_probe(self):
        compose = (Path(__file__).parents[1] / "docker-compose.yml").read_text()
        self.assertIn("http://localhost:8000/ready", compose)
        self.assertNotIn("curl -f http://localhost:8000/health", compose)

    def test_ci_validates_migrations_and_compose_configuration(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("Validate migration graph", workflow)
        self.assertIn("Validate Docker Compose configuration", workflow)
        self.assertIn("docker compose config --quiet", workflow)

    def test_webhook_signature_accepts_valid_digest(self):
        body = b'{"name":"Test Student"}'
        secret = "secret"
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertIsNone(_verify_signature(body, f"sha256={signature}", secret))

    def test_webhook_signature_rejects_invalid_digest(self):
        with self.assertRaises(HTTPException) as raised:
            _verify_signature(b"body", "sha256=invalid", "secret")
        self.assertEqual(raised.exception.status_code, 401)

    def test_financial_webhooks_require_stable_event_ids(self):
        missing_id = Request({"type": "http", "headers": []})
        with self.assertRaises(HTTPException) as raised:
            _require_event_id(missing_id)
        self.assertEqual(raised.exception.status_code, 400)

        with_id = Request({
            "type": "http",
            "headers": [(b"x-webhook-event-id", b"provider-event-1")],
        })
        self.assertEqual(_require_event_id(with_id), "provider-event-1")

    def test_offboarding_transition_chain_is_explicit(self):
        entered = transition_status(StudentStatus.COMPLETED, StudentStatus.OFFBOARDING)
        finished = transition_status(entered, StudentStatus.REFUNDED)
        self.assertEqual(entered, StudentStatus.OFFBOARDING)
        self.assertEqual(finished, StudentStatus.REFUNDED)


if __name__ == "__main__":
    unittest.main()
