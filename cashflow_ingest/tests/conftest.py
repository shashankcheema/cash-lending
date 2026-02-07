import pytest

from cashflow_ingest.api.app import app
from cashflow_ingest.ingest.pipeline.memory_sink import InMemorySink


@pytest.fixture(autouse=True)
def _reset_storage():
    app.state.storage = InMemorySink()
    yield
