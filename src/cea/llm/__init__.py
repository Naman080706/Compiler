"""LLM layer for the F3 agent (plan 010, plans/m2-architecture.md section 2).

One OpenAI-compatible client serves every provider; switching provider is a
configuration change (environment variables, see ``.env.example``). Tests use
``FakeLLM`` only and never touch the network. Nothing in this package prints.
"""
from cea.llm.base import LLMClient, LLMError
from cea.llm.cache import ExplanationCache
from cea.llm.config import client_from_env
from cea.llm.fake import FakeLLM
from cea.llm.fallback import FallbackClient
from cea.llm.openai_compat import OpenAICompatClient

__all__ = ["LLMClient", "LLMError", "OpenAICompatClient", "FallbackClient", "FakeLLM",
           "ExplanationCache", "client_from_env"]
