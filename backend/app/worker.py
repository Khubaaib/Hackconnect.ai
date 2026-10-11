"""Run hourly using a managed scheduler. No web port is required."""
import asyncio,logging
from .config import settings
from .db import open_pool,close_pool
from .main import scheduled_checks
async def run():
    settings().validate_production();await open_pool()
    try:print(await scheduled_checks())
    finally:await close_pool()
if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
