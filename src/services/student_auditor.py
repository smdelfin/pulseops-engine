# Import logging, timezone-aware clocks, typing contracts, and the ORM entity being evaluated.
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from src.models.student import Student

# Create a logger for future audit diagnostics without coupling the service to a UI.
logger = logging.getLogger(__name__)

# Encapsulate SLA policy and evaluation in a reusable, testable service.
class StudentAuditor:
    # Define program-specific time limits as (status age, follow-up age) in hours.
    SLA_CONFIG = {
        "FastTrack": (4.0, 72.0),
        "Standard": (24.0, 168.0),
        "Enterprise": (8.0, 48.0)
    }
    
    # Alert at 90 percent of the contractual threshold to leave operators response time.
    GRACE_PERIOD_BUFFER = 0.90

    # Evaluate one record and return a structured breach payload or no result.
    def evaluate_student(self, student: Student) -> Optional[Dict[str, Any]]:
        """
        Analyzes a student record for SLA breaches or missed follow-ups.
        Returns an evaluation payload if a breach is found, otherwise None.
        """
        # Exclude paused and terminal records so expected inactivity does not page operators.
        if student.is_paused or student.status in ("manual_hold", "completed", "cancelled"):
            return None

        # Select the configured program policy, falling back safely for legacy records.
        program = student.program_type or "Standard"
        status_threshold, follow_up_threshold = self.SLA_CONFIG.get(program, self.SLA_CONFIG["Standard"])
        
        # Use a timezone-aware UTC clock so comparisons are consistent across containers.
        now = datetime.now(timezone.utc)
        
        # Substitute an epoch for missing timestamps so malformed legacy rows are conservatively visible.
        status_start = student.sla_status_start_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        last_interaction = student.last_interaction_at or datetime(1970, 1, 1, tzinfo=timezone.utc)
        
        # Convert status age from seconds to hours for comparison with policy thresholds.
        status_elapsed_hours = (now - status_start).total_seconds() / 3600.0
        # Convert interaction age from seconds to hours for the follow-up policy.
        interaction_elapsed_hours = (now - last_interaction).total_seconds() / 3600.0

        # Return the first status breach with enough context for alerts and dashboards.
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

        # Otherwise return a missed-follow-up breach when the last touchpoint is too old.
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

        # Signal that this record is currently within policy and needs no alert.
        return None
