"""Allow `python -m scripts.seed` by running the seed script."""

import asyncio

from scripts.seed import _run_seed

asyncio.run(_run_seed())
