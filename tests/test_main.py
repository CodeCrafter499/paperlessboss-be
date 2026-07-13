import pytest
from httpx import AsyncClient
import sys
from pathlib import Path

# Add backend_api folder to python path so tests can find it
sys.path.insert(0, str(Path(__file__).parent.parent / "backend_api"))

from api.main import app

@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"

@pytest.mark.asyncio
async def test_validate_excel_unauthorized():
    # Calling validate-excel without authentication token should fail with 401
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/validate-excel")
    assert response.status_code == 401
