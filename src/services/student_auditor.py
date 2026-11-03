import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from src.models.student import Student

logger = logging.getLogger(__name__)

class StudentAuditor:
    # SLA Thresholds in hours
    # Format: {program_type: (status_sla, follow_up_sla)}
    SLA_CONFIG = {
        "FastTrack": (4.0, 72.0),
        "Standard": (24.0, 168.0),
        "Enterprise": (8.0, 48.0)
    }
    
    GRACE_PERIOD_BUFFER = 0.90

    def evaluate_student(self, student: Student) -> Optional[Dict[str, Any]]:
        """
        Analyzes a student record for SLA breaches or missed follow-ups.
        Returns an evaluation payload if a breach is found, otherwise None.
        """
        # False Alert Filter 1 (State Exclusion)
        if student.is_paused or student.status in ("manual_hold", "completed", "cancelled"):
            return None

        program = student.program_type or "Standard"
        status_threshold, follow_up_threshold = self.SLA_CONFIG.get(program, self.SLA_CONFIG["Standard"])
        
        now = datetime.now(timezone.utc)
        
        # Calculate elapsed times
        # If start dates are missing, we treat them as far in the past to avoid immediate alerts
        # or simply don't flag those records.
        status_start = student.sla_status_start_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        last_interaction = student.last_interaction_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        
        status_elapsed_hours = (now - status_start).total_seconds() / 3600.0
        interaction_elapsed_hours = (now - last_interaction).total_seconds() / 3600.0

        # Check SLA breaches with Grace Period Buffer
        if status_elapsed_hours > (status_threshold * self.GRACE_PERIOD_BUFFER):
            return {
                "student_id": student.id,
                "name": student.name,
                "program": program,
                "csm_id": student.assigned_csm_id,
                "breach_type": "STATUS_SLA",
                "elapsed_hours": round(status_elapsed_hours, 2),
                "threshold_hours": status_threshold
            }

        if interaction_elapsed_hours > (follow_up_threshold * self.GRACE_PERIOD_BUFFER):
            return {
                "student_id": student.id,
                "name": student.name,
                "program": program,
                "csm_id": student.assigned_csm_id,
                "breach_type": "MISSED_FOLLOWUP",
                "elapsed_hours": round(interaction_elapsed_hours, 2),
                "threshold_hours": follow_up_threshold
            }

        return None
