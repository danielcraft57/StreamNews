"""Fixtures partagees (integration Postgres)."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATABASE_URL = os.getenv("DATABASE_URL", "")


@pytest.fixture(scope="module")
def database_url():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL non defini (integration Postgres)")
    return DATABASE_URL


@pytest.fixture
async def db(database_url):
    # Import apres le path : asyncpg reel (ne pas mocker ici)
    from database import Database

    d = Database()
    d.database_url = database_url
    await d.init_db(reset=True)
    yield d
    await d.pool.close()


@pytest.fixture
async def site_id(db):
    result = await db.upsert_site_for_analysis("https://example.com/", "pending")
    return result["site_id"]
