# Import retry timing, diagnostics, HTTP transport, and type contracts for ClickUp calls.
import asyncio
import logging
import time
import httpx
from typing import Dict, Any, Optional

# Import validated credentials and integration settings from the shared configuration boundary.
from ..core.config import settings

# Create a logger that records external API outcomes with correlation identifiers.
logger = logging.getLogger(__name__)

# Represent all ClickUp failures under one application-specific exception family.
class ClickUpAPIError(Exception):
    """Base exception for ClickUp API errors."""
    pass

# Represent provider throttling separately so callers can distinguish backpressure from bad input.
class ClickUpRateLimitError(ClickUpAPIError):
    """Raised when a 429 Rate Limit error occurs."""
    pass

# Represent exhausted network timeout retries separately for operational handling.
class ClickUpTimeoutError(ClickUpAPIError):
    """Raised when a network timeout occurs."""
    pass

class ClickUpClient:
    # Initialize immutable transport configuration for one ClickUp API client.
    def __init__(self):
        # Keep the provider base URL centralized so endpoint methods only specify resource paths.
        self.base_url = "https://api.clickup.com/api/v2"
        # Send the configured token and JSON content type on every request.
        self.headers = {
            "Authorization": settings.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }
        # Bound connect and response waits so a provider outage cannot stall a worker forever.
        self.timeout = httpx.Timeout(10.0, connect=5.0, read=10.0)

    async def _request_with_retry(
        self, 
        method: str, 
        endpoint: str, 
        json_data: Optional[Dict[str, Any]] = None,
        student_id: str = "N/A",
        ghl_contact_id: str = "N/A",
        attempt: int = 1
    ) -> Dict[str, Any]:
        """
        Internal helper to handle retries, rate limits, and logging.
        """
        # Combine the resource path with the provider base URL.
        url = f"{self.base_url}{endpoint}"
        
        # Create an async HTTP client for the request and ensure its sockets are closed afterward.
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            try:
                # Start a monotonic timer so latency is not affected by wall-clock changes.
                start_time = time.perf_counter()
                # Execute the outbound request without blocking the event loop.
                response = await client.request(method, url, json=json_data)
                # Convert elapsed monotonic time to milliseconds for structured logs.
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code == 429:
                    # Read the provider's backoff hint and use a safe default when it is absent.
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        f"[ClickUp RateLimit] Rate limit exceeded on task creation for student_id={student_id}. "
                        f"Backing off for {retry_after} seconds. (Attempt {attempt}/3)"
                    )
                    if attempt < 3:
                        # Wait before retrying so the client respects provider backpressure.
                        await asyncio.sleep(retry_after)
                        # Re-enter the same helper with an incremented attempt counter.
                        return await self._request_with_retry(
                            method, endpoint, json_data, student_id, ghl_contact_id, attempt + 1
                        )
                    # Stop after the retry budget so one throttled request cannot loop forever.
                    raise ClickUpRateLimitError(f"Rate limit exceeded after {attempt} attempts.")

                # Convert non-success HTTP statuses into an explicit exception.
                response.raise_for_status()
                
                # Record request identity and latency for production troubleshooting.
                logger.info(
                    f"ClickUp Request Success | student_id={student_id} | "
                    f"ghl_contact_id={ghl_contact_id} | "
                    f"status={response.status_code} | latency={latency_ms:.2f}ms"
                )
                # Deserialize the provider response into the caller's expected mapping.
                return response.json()

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                # Measure the failed attempt using the same monotonic timer.
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"[ClickUp Timeout] Request timed out connecting to ClickUp for student_id={student_id} "
                    f"after {latency_ms:.2f}ms. Attempt {attempt}/3. Error: {e}"
                )
                if attempt < 3:
                    # Apply exponential backoff so transient failures do not create a request storm.
                    await asyncio.sleep(2 ** attempt)  # Simple exponential backoff
                    # Retry with the same payload and a larger attempt number.
                    return await self._request_with_retry(
                        method, endpoint, json_data, student_id, ghl_contact_id, attempt + 1
                    )
                # Surface exhausted connectivity failures to the provisioning workflow.
                raise ClickUpTimeoutError(f"Timeout exceeded after {attempt} attempts.")
            
            except httpx.HTTPStatusError as e:
                # Preserve provider status and body in logs while normalizing the exception type.
                logger.error(f"HTTP Error for student_id={student_id}: {e.response.status_code} - {e.response.text}")
                raise ClickUpAPIError(f"HTTP error occurred: {e}")

    # Create the per-student ClickUp list used as the external onboarding workspace.
    async def create_student_list(self, student_name: str, cohort: str, student_id: str, ghl_contact_id: str) -> Dict[str, Any]:
        """Creates a list/folder for a student in ClickUp."""
        # Select the provider endpoint for list creation.
        endpoint = "/list"
        # Build the provider payload from domain values and configured team scope.
        payload = {
            "name": f"Student: {student_name}",
            "description": f"Cohort: {cohort}",
            "team": settings.CLICKUP_TEAM_ID
        }
        # Delegate transport, retries, and logging to the shared request helper.
        return await self._request_with_retry("POST", endpoint, payload, student_id, ghl_contact_id)

    # Create an actionable ClickUp task inside an existing student list.
    async def create_task(
        self, 
        list_id: str, 
        task_name: str, 
        description: str, 
        assignee_id: str = None,
        student_id: str = "N/A",
        ghl_contact_id: str = "N/A"
    ) -> Dict[str, Any]:
        """Creates a task in a specific ClickUp list."""
        # Select the provider endpoint for task creation.
        endpoint = "/task"
        # Translate application fields into ClickUp's JSON contract.
        payload = {
            "name": task_name,
            "description": description,
            "list_id": list_id,
            "assignee": assignee_id
        }
        # Use the common transport path so list and task creation behave consistently.
        return await self._request_with_retry("POST", endpoint, payload, student_id, ghl_contact_id)
