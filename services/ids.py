from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

COUNTERS_COLLECTION = "counters"


async def get_next_sequence(db: AsyncIOMotorDatabase, name: str) -> int:
    doc = await db[COUNTERS_COLLECTION].find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
        return_document=True,
    )
    return int(doc["seq"])
