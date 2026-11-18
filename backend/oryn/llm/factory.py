from oryn.core.config import Settings
from oryn.core.logging import log
from oryn.llm.types import LLMProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.effective_llm_provider == "anthropic" and settings.anthropic_api_key:
        import anthropic

        from oryn.llm.anthropic_provider import AnthropicProvider

        log.info("llm.provider", provider="anthropic")
        return AnthropicProvider(anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()))
    from oryn.llm.replay.provider import ReplayProvider

    return ReplayProvider()
