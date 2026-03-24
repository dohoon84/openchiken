"""
OpenChiken LLM Provider
────────────────────────
LLM 공급자 추상화. settings.llm_provider 값으로 실제 모델을 선택합니다.

지원 공급자:
  openai    — ChatOpenAI (기본값, langchain-openai)
  anthropic — ChatAnthropic (langchain-anthropic 필요)
  gemini    — ChatGoogleGenerativeAI (langchain-google-genai 필요)
  ollama    — ChatOllama (langchain-ollama 필요, 로컬 실행)

추가 공급자:
  LLMProvider를 상속받아 get_model()을 구현하고,
  _PROVIDERS 딕셔너리에 이름을 등록하면 됩니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel

from config.settings import settings


class LLMProvider(ABC):
    @abstractmethod
    def get_model(self) -> BaseChatModel: ...


class OpenAIProvider(LLMProvider):
    def get_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )


class AnthropicProvider(LLMProvider):
    def get_model(self) -> BaseChatModel:
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ImportError(
                "langchain-anthropic 패키지가 필요합니다: uv add langchain-anthropic"
            ) from exc
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.3,
        )


class GeminiProvider(LLMProvider):
    def get_model(self) -> BaseChatModel:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ImportError(
                "langchain-google-genai 패키지가 필요합니다: uv add langchain-google-genai"
            ) from exc
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.3,
        )


class OllamaProvider(LLMProvider):
    def get_model(self) -> BaseChatModel:
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ImportError(
                "langchain-ollama 패키지가 필요합니다: uv add langchain-ollama"
            ) from exc
        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.3,
        )


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai":     OpenAIProvider,
    "anthropic":  AnthropicProvider,
    "gemini":     GeminiProvider,
    "ollama":     OllamaProvider,
}

_provider_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """settings.llm_provider 기반으로 LLMProvider 싱글턴을 반환합니다."""
    global _provider_instance
    if _provider_instance is None:
        name = settings.llm_provider
        cls = _PROVIDERS.get(name)
        if cls is None:
            raise ValueError(
                f"알 수 없는 LLM 공급자: '{name}'. 지원 값: {list(_PROVIDERS)}"
            )
        _provider_instance = cls()
    return _provider_instance
