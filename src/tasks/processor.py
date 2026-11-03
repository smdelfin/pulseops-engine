# Import the canonical worker entrypoint instead of maintaining a second incompatible queue loop.
from ..workers.provisioning_worker import main_worker

# Preserve the historical processor entrypoint as a compatibility wrapper.
async def process_queue():
    await main_worker()

if __name__ == "__main__":
    import asyncio
    asyncio.run(process_queue())
