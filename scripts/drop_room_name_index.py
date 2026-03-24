from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

# Ensure project root is on sys.path so `import app.*` works when running this
# script from the `scripts/` folder.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.db.init_db import MATCHES_COLLECTION


async def main() -> None:
    client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    )
    db = client[settings.DATABASE_NAME]
    coll = db[MATCHES_COLLECTION]

    info = await coll.index_information()
    print("indexes", sorted(info.keys()))

    for name in ("uq_matches_room_name", "idx_matches_room_name"):
        if name in info:
            try:
                await coll.drop_index(name)
                print("dropped", name)
            except Exception as exc:
                print("drop_failed", name, type(exc).__name__, str(exc)[:200])

    await coll.create_index([("room_name", 1)], name="idx_matches_room_name")

    info2 = await coll.index_information()
    print("indexes_after", sorted(info2.keys()))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
