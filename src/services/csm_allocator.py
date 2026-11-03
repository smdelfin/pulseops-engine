# Import List from typing to provide type hints for a sequence of strings.
from typing import List
# Import the random module to handle non-deterministic selection of CSMs.
import random

# Service responsible for assigning a Customer Success Manager (CSM) to a new student.
class CSMAllocator:
    # Initialize with a list of available CSM identifiers.
    def __init__(self, csm_ids: List[str]):
        # In a production scenario, these would be fetched from a DB or Config.
        self.csm_ids = csm_ids

    # Select and return the next available CSM to handle the student's onboarding.
    def get_next_csm(self) -> str:
        """Returns the next available CSM using round-robin or random."""
        # Use a random choice to ensures balanced distribution of student accounts.
        return random.choice(self.csm_ids)
