# Import logging so queue connectivity and retry behavior are visible to operators.
import logging
# Import Azure's base error type to handle service-level failures explicitly.
from azure.core.exceptions import AzureError
# Import the async queue client so webhook requests can enqueue work without blocking FastAPI.
from azure.storage.queue.aio import QueueClient

# Import validated settings so credentials remain outside source code.
from src.core.config import settings

# Create a module-scoped logger for queue health and delivery diagnostics.
logger = logging.getLogger(__name__)

# Encapsulate Azure Queue operations behind a small application-level service.
class QueueService:
    # Construct one reusable client configured for the provisioning queue.
    def __init__(self) -> None:
        self.queue_client = QueueClient.from_connection_string(
            conn_str=settings.AZURE_STORAGE_CONNECTION_STRING,
            queue_name="student-provisioning",
        )

    # Publish a serialized work item so the API and worker are decoupled in time.
    async def push_message(self, message_body: str) -> None:
        # Import asyncio locally because it is only needed by the retry path.
        import asyncio
        # Import the transient request exception used to distinguish connection failures.
        from azure.core.exceptions import ServiceRequestError
        # Permit a bounded number of attempts so outages do not create an infinite request.
        for attempt in range(3):
            try:
                # Ensure first-use deployments have the target queue before sending a message.
                await self.queue_client.create_queue()
            except AzureError:
                # Treat an existing queue or provisioning race as non-fatal and continue to send.
                pass
            
            try:
                # Send the message; Azure persists it until a worker consumes it.
                await self.queue_client.send_message(message_body)
                return
            except (ServiceRequestError, AzureError, ConnectionRefusedError) as e:
                # Re-raise after the final attempt so the caller can restore database state.
                if attempt == 2:
                    raise
                # Log bounded exponential backoff so operators can distinguish retrying from failure.
                logger.warning("[Queue Disconnect] Lost connection to queue: %s. Retrying in %ds...", e, 2 ** (attempt + 1))
                # Yield to the event loop while waiting for a transient Azure outage to clear.
                await asyncio.sleep(2 ** (attempt + 1))

    async def dead_letter_message(self, message_body: str) -> None:
        dead_letter_client = QueueClient.from_connection_string(
            conn_str=settings.AZURE_STORAGE_CONNECTION_STRING,
            queue_name="student-provisioning-deadletter",
        )
        try:
            await dead_letter_client.create_queue()
            await dead_letter_client.send_message(message_body)
        finally:
            await dead_letter_client.close()

    # Close the async client so sockets and other transport resources are released on shutdown.
    async def close(self) -> None:
        await self.queue_client.close()
