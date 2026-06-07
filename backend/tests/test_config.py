from app.core.config import Settings, _get_csv_env


def test_settings_loads_default_values() -> None:
    settings = Settings()

    assert settings.app_name == "NLP2SQL Agent API"
    assert settings.app_version == "0.1.0"
    assert settings.db_schema == "public"
    assert settings.sql_default_limit > 0
    assert settings.sql_max_limit >= settings.sql_default_limit
    assert settings.sql_executor_max_rows > 0
    assert "http://localhost:5173" in settings.cors_origins


def test_csv_env_parser_strips_empty_values(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:5173, ,http://localhost:3000,, ")

    assert _get_csv_env("CORS_ORIGINS", "") == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
