import asyncio
import logging
import time
import httpx
from typing import Dict, Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

class ClickUpAPIError(Exception):
    """Base exception for ClickUp API errors."""
    pass

class ClickUpRateLimitError(ClickUpAPIError):
    """Raised when a 429 Rate Limit error occurs."""
    pass

class ClickUpTimeoutError(ClickUpAPIError):
    """Raised when a network timeout occurs."""
    pass

class ClickUpClient:
    def __init__(self):
        self.base_url = "https://api.clickup.com/api/v2"
        self.headers = {
            "Authorization": settings.CLICKUP_API_TOKEN,
            "Content-Type": "application/json"
        }
        # Standard timeout configuration: overall 10s, connect 5s, read 10s
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
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            try:
                start_time = time.perf_counter()
                response = await client.request(method, url, json=json_data)
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code == 429:
                    # Extract retry info
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        f"[ClickUp RateLimit] Rate limit exceeded on task creation for student_id={student_id}. "
                        f"Backing off for {retry_after} seconds. (Attempt {attempt}/3)"
                    )
                    if attempt < 3:
                        await asyncio.sleep(retry_after)
                        return await self._request_with_retry(
                            method, endpoint, json_data, student_id, ghl_contact_id, attempt + 1
                        )
                    raise ClickUpRateLimitError(f"Rate limit exceeded after {attempt} attempts.")

                response.raise_for_status()
                
                # Structured log for success
                logger.info(
                    f"ClickUp Request Success | student_id={student_id} | "
                    f"ghl_contact_id={ghl_contact_id} | "
                    f"status={response.status_code} | latency={latency_ms:.2f}ms"
                )
                return response.json()

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"[ClickUp Timeout] Request timed out connecting to ClickUp for student_id={student_id} "
                    f"after {latency_ms:.2f}ms. Attempt {attempt}/3. Error: {e}"
                )
                if attempt < 3:
                    await asyncio.sleep(2 ** attempt)  # Simple exponential backoff
                    return await self._request_with_retry(
                        method, endpoint, json_data, student_id, ghl_contact_id, attempt + 1
                    )
                raise ClickUpTimeoutError(f"Timeout exceeded after {attempt} attempts.")
            
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP Error for student_id={student_id}: {e.response.status_code} - {e.response.text}")
                raise ClickUpAPIError(f"HTTP error occurred: {e}")

    async def create_student_list(self, student_name: str, cohort: str, student_id: str, ghl_contact_id: str) -> Dict[str, Any]:
        """Creates a list/folder for a student in ClickUp."""
        endpoint = "/list"
        payload = {
            "name": f"Student: {student_name}",
            "description": f"Cohort: {cohort}",
            "team": settings.CLICKUP_TEAM_ID
        }
        return await self._request_with_retry("POST", endpoint, payload, student_id, ghl_contact_id)

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
        endpoint = "/task"
        payload = {
            "name": task_name,
            "description": description,
            "list_id": list_id,
            "assignee": assignee_id
        }
        return await self._request_with_retry("POST", endpoint, payload, student_id, ghl_contact_id)
