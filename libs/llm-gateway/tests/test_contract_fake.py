import pytest

from pokedex_llm import FakeLLM
from pokedex_llm.contract import GatewayContract


class TestFakeLLMContract(GatewayContract):
    @pytest.fixture
    def gateway(self) -> FakeLLM:
        return FakeLLM()
