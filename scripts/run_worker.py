import sys
import os
import asyncio
import logging
import traceback

# Add project root to sys.path to handle imports correctly
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.workers.provisioning_worker import main

# Set up logging for crash reporting
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        logger.critical("[Worker Fatal] Worker process crashed: %s", err, exc_info=True)
        sys.exit(1)

