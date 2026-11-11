import pytest


@pytest.fixture(autouse=True)
def fresh_result_cache(monkeypatch):
    """Cache em memoria e vazio a cada teste: nada grava na tabela DynamoDB real do .env."""
    import importlib
    app_module = importlib.import_module("src.api.app")
    from src.aws.cache import ResultCache
    monkeypatch.setattr(app_module, "result_cache", ResultCache(table_name=""))
