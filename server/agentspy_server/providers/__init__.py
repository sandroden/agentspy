"""Registry degli adapter provider.

Il provider attivo si sceglie con AGENTSPY_PROVIDER (default: anthropic).
Per aggiungerne uno: implementare ProviderAdapter in un modulo qui accanto
e registrarlo in PROVIDERS.
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
            f"provider sconosciuto: {name!r} (disponibili: {', '.join(sorted(PROVIDERS))})"
        ) from None


__all__ = ["ProviderAdapter", "StreamCollector", "PROVIDERS", "get_provider"]
