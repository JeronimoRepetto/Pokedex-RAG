"""Live contract run against the real Vertex adapter. Never in CI.

RUN_INTEGRATION=1 poetry run pytest -m live tests/test_contract_live.py
"""

import os

import pytest

from pokedex_llm import VertexGeminiAdapter
from pokedex_llm.contract import GatewayContract

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE") != "1",
        reason="live contract test: set RUN_LIVE=1 with ADC configured (costs ~$0.001)",
    ),
]


class TestVertexGeminiContract(GatewayContract):
    @pytest.fixture
    def gateway(self) -> VertexGeminiAdapter:
        return VertexGeminiAdapter(
            project=os.environ.get("GCP_PROJECT_ID", "pokedex-rag-504617"),
            location=os.environ.get("GENERATION_LOCATION", "global"),
            model=os.environ.get("GENERATION_MODEL", "gemini-3.6-flash"),
        )
