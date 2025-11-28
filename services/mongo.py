import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from core.config import settings

logger = logging.getLogger(__name__)


def create_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongodb_uri)


def get_database(client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    return client[settings.mongodb_dbname]


async def lifespan(app):
    client = create_mongo_client()
    app.state.mongo_client = client
    app.state.mongo_db = get_database(client)
    
    # Initialize public API key at startup
    from services.submissions import ensure_public_api_key
    try:
        await ensure_public_api_key(app.state.mongo_db)
        logger.info("Public API key initialized")
    except Exception as e:
        logger.warning("Failed to initialize public API key (will use fallback): %s", e)
        # Don't block application startup, will use code constants as fallback
    
    try:
        yield
    finally:
        client.close()


def get_db(app) -> AsyncIOMotorDatabase:
    return app.state.mongo_db
