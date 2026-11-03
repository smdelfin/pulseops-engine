import hashlib
import hmac
import os
import unittest


os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/pulseops")
os.environ.setdefault("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
os.environ.setdefault("CLICKUP_API_TOKEN", "test-token")
os.environ.setdefault("CLICKUP_DEFAULT_LIST_ID", "test-list")
os.environ.setdefault("GHL_WEBHOOK_SECRET", "ghl-secret")
os.environ.setdefault("CLICKUP_WEBHOOK_SECRET", "clickup-secret")

from src.api.webhooks import _verify_signature
from src.models.student import Student
from src.services.student_auditor import StudentAuditor
from src.domain.lifecycle import InvalidStudentTransition, StudentDomainEvent, StudentStatus, transition_status
from src.models.messaging import InboxEvent, OutboxEvent
from fastapi import HTTPException


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

    def test_webhook_signature_accepts_valid_digest(self):
        body = b'{"name":"Test Student"}'
        secret = "secret"
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertIsNone(_verify_signature(body, f"sha256={signature}", secret))

    def test_webhook_signature_rejects_invalid_digest(self):
        with self.assertRaises(HTTPException) as raised:
            _verify_signature(b"body", "sha256=invalid", "secret")
        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
