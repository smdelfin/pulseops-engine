# Runtime: Provides command-line and process configuration access.
# Architecture: Supports direct execution of the worker launcher.
# Plain English: Supplies system-level helpers.
import sys
# Runtime: Provides filesystem path operations.
# Architecture: Locates the repository root for application imports.
# Plain English: Works with paths.
import os
# Runtime: Provides the event-loop runner for asynchronous work.
# Architecture: Matches the async database and Azure queue stack.
# Plain English: Runs coroutine-based code.
import asyncio
# Runtime: Provides structured logging for process diagnostics.
# Architecture: Sends worker lifecycle information to container logs.
# Plain English: Writes operational messages.
import logging
# Runtime: Provides traceback support for diagnostic tooling.
# Architecture: Keeps stack-trace utilities available to the launcher.
# Plain English: Supports detailed error reporting.
import traceback

# Runtime: Adds the project root to Python's module search path.
# Architecture: Makes the src package importable when this file is run directly.
# Plain English: Tells Python where the application code is.
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.workers.provisioning_worker import main

# Runtime: Configures process-wide INFO logging with a consistent timestamped format.
# Architecture: Makes worker events visible to Docker/Azure supervision.
# Plain English: Sets up readable crash and lifecycle logs.
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# Runtime: Creates a module-specific logger for fatal errors.
# Architecture: Preserves the worker launcher's identity in aggregated logs.
# Plain English: Gives this script a named logger.
logger = logging.getLogger(__name__)

# Runtime: Prevents startup side effects when the launcher is imported.
# Architecture: Keeps orchestration and tests in control of worker execution.
# Plain English: Runs this block only when launched directly.
if __name__ == "__main__":
    # Runtime: Wraps the worker lifetime so escaped failures are logged and surfaced.
    # Architecture: Gives process supervisors a clear failure signal.
    # Plain English: Watches the worker startup and run.
    try:
        # Runtime: Creates an event loop and runs the imported worker coroutine.
        # Architecture: Hosts asynchronous provisioning and queue processing.
        # Plain English: Starts the worker.
        asyncio.run(main())
    # Runtime: Handles exceptions that escape the worker's own logic.
    # Architecture: Records a full traceback before terminating unhealthy workers.
    # Plain English: Reports a crash instead of hiding it.
    except Exception as err:
        logger.critical("[Worker Fatal] Worker process crashed: %s", err, exc_info=True)
        # Runtime: Exits with failure status for Docker/Azure restart policies.
        # Architecture: Lets orchestration distinguish a crash from normal completion.
        # Plain English: Marks the process as failed.
        sys.exit(1)
