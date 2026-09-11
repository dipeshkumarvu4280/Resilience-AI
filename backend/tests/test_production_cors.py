import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings, Settings


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_cors_production_vercel_origin_allowed(client):
    """Verify that the production Vercel frontend origin receives CORS headers."""
    origin = "https://resilience-ai-pied.vercel.app"
    response = client.get("/", headers={"Origin": origin})
    
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_local_dev_origins_allowed(client):
    """Verify that localhost and 127.0.0.1 origins remain allowed."""
    for origin in ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]:
        response = client.get("/", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == origin
        assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_unknown_origin_rejected(client):
    """Verify that unauthorized/unknown origins do not receive Access-Control-Allow-Origin."""
    unknown_origin = "https://unauthorized-attacker-site.com"
    response = client.get("/", headers={"Origin": unknown_origin})
    
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_options_preflight_request(client):
    """Verify OPTIONS preflight request from production Vercel frontend."""
    origin = "https://resilience-ai-pied.vercel.app"
    response = client.options(
        "/api/v1/system/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type,Accept",
        },
    )
    
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"
    allow_methods = response.headers.get("access-control-allow-methods", "")
    assert "GET" in allow_methods
    assert "POST" in allow_methods
    assert "OPTIONS" in allow_methods


def test_cors_authenticated_request_with_authorization_header(client):
    """Verify that authenticated requests retain CORS headers."""
    origin = "https://resilience-ai-pied.vercel.app"
    response = client.get(
        "/api/v1/users/me",
        headers={
            "Origin": origin,
            "Authorization": "Bearer invalid_or_sample_token",
        },
    )
    
    # Even if 401 Unauthorized, CORS headers MUST be present
    assert response.status_code == 401
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_error_response_404(client):
    """Verify 404 Not Found response still includes CORS headers."""
    origin = "https://resilience-ai-pied.vercel.app"
    response = client.get("/api/v1/nonexistent-endpoint-xyz", headers={"Origin": origin})
    
    assert response.status_code == 404
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_error_response_422(client):
    """Verify 422 Unprocessable Entity response retains CORS headers."""
    origin = "https://resilience-ai-pied.vercel.app"
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": origin, "Content-Type": "application/json"},
        json={"invalid": "data"},
    )
    
    assert response.status_code == 422
    assert response.headers.get("access-control-allow-origin") == origin
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_no_wildcard_with_credentials():
    """Verify settings.cors_origins never contains wildcard '*' when credentials are true."""
    for origin in settings.cors_origins:
        assert origin != "*"
        assert not origin.endswith("/")  # No trailing slashes


def test_cors_settings_flexible_env_parsing():
    """Verify comma-separated and JSON list parsing in Settings."""
    custom_settings = Settings(
        CORS_ALLOWED_ORIGINS="https://preview-app.vercel.app, https://custom-domain.org/",
        BACKEND_CORS_ORIGINS=["http://localhost:5173"],
    )
    origins = custom_settings.cors_origins
    assert "https://preview-app.vercel.app" in origins
    assert "https://custom-domain.org" in origins
    assert "https://resilience-ai-pied.vercel.app" in origins
    assert "http://localhost:5173" in origins
