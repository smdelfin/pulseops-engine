# Import logging to record events, errors, and operational statuses.
import logging
# Import AzureError to catch specific connection or communication issues with Azure Storage.
from azure.core.exceptions import AzureError
# Import the asynchronous QueueClient to support non-blocking message operations.
from azure.storage.queue.aio import QueueClient

# Import configuration to access the connection string and mandatory queue identifiers.
from src.core.config import settings

# Initialize a logger for this module to track queue health and message status.
logger = logging.getLogger(__name__)

# Service to manage asynchronous interactions with Azure Storage Queues.
class QueueService:
    # Instantiate the client using the connection string provided in the environment configuration.
    def __init__(self) -> None:
        self.queue_client = QueueClient.from_connection_string(
            conn_str=settings.AZURE_STORAGE_CONNECTION_STRING,
            queue_name="student-provisioning",
        )

    # Push a plain-text message (typically a JSON string) into the task queue.
    async def push_message(self, message_body: str) -> None:
        import asyncio
        from azure.core.exceptions import ServiceRequestError
        for attempt in range(3):
            try:
                # Ensure the designated queue exists in the storage account.
                await self.queue_client.create_queue()
            except AzureError:
                # Pass if queue already exists; ignore to ensure continuity.
                pass
            
            try:
                # Execute the send operation to enqueue the student provisioning task.
                await self.queue_client.send_message(message_body)
                return
            except (ServiceRequestError, AzureError, ConnectionRefusedError) as e:
                if attempt == 2:
                    raise
                logger.warning("[Queue Disconnect] Lost connection to queue: %s. Retrying in %ds...", e, 2 ** (attempt + 1))
                await asyncio.sleep(2 ** (attempt + 1))

    # Gracefully shut down the client to release network connections and resources.
    async def close(self) -> None:
        await self.queue_client.close()
