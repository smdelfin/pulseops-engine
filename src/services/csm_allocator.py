# Import List so the allocator's input and output contract is visible to readers and type checkers.
from typing import List
# Import random to distribute assignments without requiring a database-backed scheduler.
import random

# Encapsulate CSM assignment policy so provisioning does not know how people are selected.
class CSMAllocator:
    # Accept the currently eligible CSM identifiers from configuration or a future database query.
    def __init__(self, csm_ids: List[str]):
        # Keep the candidate pool on the service for each assignment decision.
        self.csm_ids = csm_ids

    # Select one eligible owner so each new onboarding task has a responsible human.
    def get_next_csm(self) -> str:
        """Returns the next available CSM using round-robin or random."""
        # Random selection spreads work in this lightweight implementation without shared counters.
        return random.choice(self.csm_ids)
