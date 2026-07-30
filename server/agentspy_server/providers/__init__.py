"""Registry of the provider adapters.

The active provider is selected with AGENTSPY_PROVIDER (default: anthropic).
To add one: implement ProviderAdapter in a module next to this one and
register it in PROVIDERS.
"""

from __future__ import annotations

import os

from .anthropic import AnthropicAdapter
from .base import ProviderAdapter, StreamCollector

PROVIDERS: dict[str, type[ProviderAdapter]] = {
    "anthropic": AnthropicAdapter,
}


def get_provider(name: str | None = None) -> ProviderAdapter:
    name = name or os.environ.get("AGENTSPY_PROVIDER", "anthropic")
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise ValueError(
            f"unknown provider: {name!r} (available: {', '.join(sorted(PROVIDERS))})"
        ) from None


__all__ = ["ProviderAdapter", "StreamCollector", "PROVIDERS", "get_provider"]
