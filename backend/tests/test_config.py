from backend.app.core.config import Settings


def test_settings_initialization():
    """
    Verify Settings loads default attributes properly and provides database url.
    """
    test_settings = Settings(
        PROJECT_NAME="Test Document Intelligence",
        ENVIRONMENT="test",
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_SERVER="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="test_db"
    )

    assert test_settings.PROJECT_NAME == "Test Document Intelligence"
    assert test_settings.ENVIRONMENT == "test"
    assert "postgresql+asyncpg://test_user:test_password@localhost:5432/test_db" in test_settings.async_database_url


def test_cors_origins_parsing():
    """
    Verify CORS origins can parse string or list inputs.
    """
    settings_from_str = Settings(
        BACKEND_CORS_ORIGINS="http://localhost:3000,http://localhost:8000"  # type: ignore
    )
    assert len(settings_from_str.BACKEND_CORS_ORIGINS) == 2
    assert "http://localhost:3000" in settings_from_str.BACKEND_CORS_ORIGINS
