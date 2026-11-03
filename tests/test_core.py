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
from fastapi import HTTPException


class CoreBehaviorTests(unittest.TestCase):
    def test_student_model_contains_pause_flag(self):
        self.assertIn("is_paused", Student.__table__.columns)
        self.assertFalse(Student.__table__.c.is_paused.nullable)

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
