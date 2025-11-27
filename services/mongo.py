
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from core.config import settings


def create_mongo_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(settings.mongodb_uri)


def get_database(client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    return client[settings.mongodb_dbname]


async def lifespan(app):
    client = create_mongo_client()
    app.state.mongo_client = client
    app.state.mongo_db = get_database(client)
    try:
        yield
    finally:
        client.close()


def get_db(app) -> AsyncIOMotorDatabase:
    return app.state.mongo_db
