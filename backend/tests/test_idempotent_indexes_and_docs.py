import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from pymongo import IndexModel, ASCENDING
from pymongo.errors import OperationFailure

from app.main import app
from app.db.mongodb import safe_create_indexes_for_collection, init_db_indexes


def test_docs_and_openapi_routes_accessible():
    """Verify GET /docs, GET /openapi.json, GET /redoc and redirects."""
    client = TestClient(app, raise_server_exceptions=False)
    
    # 1. GET / returns operational status with api_docs pointing to /docs
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    data = resp_root.json()
    assert data["status"] == "OPERATIONAL"
    assert data["api_docs"] == "/docs"
    assert data["openapi_url"] == "/openapi.json"

    # 2. GET /docs returns HTML (Swagger UI)
    resp_docs = client.get("/docs")
    assert resp_docs.status_code == 200
    assert "text/html" in resp_docs.headers.get("content-type", "")
    assert "swagger" in resp_docs.text.lower() or "openapi" in resp_docs.text.lower()

    # 3. GET /openapi.json returns valid JSON OpenAPI specification
    resp_openapi = client.get("/openapi.json")
    assert resp_openapi.status_code == 200
    openapi_schema = resp_openapi.json()
    assert "openapi" in openapi_schema or "swagger" in openapi_schema
    assert "paths" in openapi_schema

    # 4. GET /redoc returns HTML (ReDoc UI)
    resp_redoc = client.get("/redoc")
    assert resp_redoc.status_code == 200
    assert "text/html" in resp_redoc.headers.get("content-type", "")

    # 5. Backward compatibility redirects
    resp_api_docs = client.get("/api/docs", follow_redirects=False)
    assert resp_api_docs.status_code in [301, 302, 307, 308]
    assert resp_api_docs.headers.get("location") == "/docs"

    resp_api_openapi = client.get("/api/openapi.json", follow_redirects=False)
    assert resp_api_openapi.status_code in [301, 302, 307, 308]
    assert resp_api_openapi.headers.get("location") == "/openapi.json"


@pytest.mark.asyncio
async def test_safe_create_indexes_handles_index_conflict_reconciliation():
    """
    Simulate MongoDB IndexKeySpecsConflict on idx_coordination_plans_pending_fingerprint.
    Verify reconciliation:
    1. First create_indexes raises IndexKeySpecsConflict (code 85 / IndexKeySpecsConflict)
    2. safe_create_indexes_for_collection catches it
    3. Finds and drops the stale index by name
    4. Recreates index with clean target definition
    5. Zero document deletion
    """
    mock_col = MagicMock()
    mock_col.name = "coordination_plans"
    
    # Existing stale index info in MongoDB
    mock_col.index_information = AsyncMock(return_value={
        "_id_": {"key": [("_id", 1)]},
        "idx_coordination_plans_pending_fingerprint": {
            "key": [("situation_id", 1), ("state_fingerprint", 1)],
            "unique": True,
            "partialFilterExpression": {"status": {"$eq": "PENDING_OFFICER_REVIEW"}}, # stale format
        }
    })
    mock_col.drop_index = AsyncMock()

    # First attempt raises IndexKeySpecsConflict, second attempt succeeds
    conflict_err = OperationFailure(
        "Index with name: idx_coordination_plans_pending_fingerprint already exists with different options "
        "(IndexKeySpecsConflict)",
        code=85
    )
    mock_col.create_indexes = AsyncMock(side_effect=[conflict_err, ["idx_coordination_plans_pending_fingerprint"]])

    target_index_model = IndexModel(
        [("situation_id", ASCENDING), ("state_fingerprint", ASCENDING)],
        unique=True,
        partialFilterExpression={"status": "PENDING_OFFICER_REVIEW", "state_fingerprint": {"$type": "string"}},
        name="idx_coordination_plans_pending_fingerprint",
    )

    await safe_create_indexes_for_collection(mock_col, [target_index_model])

    # Assertions
    assert mock_col.create_indexes.call_count == 2
    mock_col.drop_index.assert_called_once_with("idx_coordination_plans_pending_fingerprint")


@pytest.mark.asyncio
async def test_safe_create_indexes_idempotent_on_repeat():
    """Verify that when no conflict exists, create_indexes is called cleanly without dropping."""
    mock_col = MagicMock()
    mock_col.name = "users"
    mock_col.create_indexes = AsyncMock(return_value=["idx_users_phone_unique"])
    mock_col.drop_index = AsyncMock()

    target_index_model = IndexModel([("phone", ASCENDING)], unique=True, name="idx_users_phone_unique")

    await safe_create_indexes_for_collection(mock_col, [target_index_model])

    assert mock_col.create_indexes.call_count == 1
    assert mock_col.drop_index.call_count == 0
