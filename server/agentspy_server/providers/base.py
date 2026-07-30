"""Provider layer: isolates the LLM provider's wire protocol.

agentspy persists and renders an internal "neutral" model that is deliberately
derived from Anthropic's Messages API:

- the reconstructed response is a ``message`` with ``content`` made of typed
  blocks (``text``, ``thinking``, ``tool_use``, ``tool_result``, ``image``);
- the usage in the DB columns uses neutral names (``input_tokens``,
  ``output_tokens``, ``cache_read_tokens``, ``cache_write_tokens``).

An adapter for another provider (e.g. OpenAI Responses API) must TRANSLATE its
own wire format into this model at ingest time: for Anthropic the translation
is (almost) the identity, so the payloads already saved stay valid without a
migration. The raw request body stays persisted exactly as it went over the
wire — it is the educational material — while everything the rest of the system
*interprets* (round trip yes/no, analysis, response blocks, usage) goes through
this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StreamCollector(ABC):
    """Reconstructs the model response from a byte stream (e.g. SSE).

    ``finalize()`` must return a dict in the neutral model:
    ``{"type": ..., "message": {..., "content": [blocks]}, "usage": {...},
    "stop_reason": ..., "events_count": {...}}`` plus an optional ``"error"``.
    ``usage`` may use the provider's wire names: the translation into the
    neutral names happens with ``ProviderAdapter.normalize_usage``.
    """

    @abstractmethod
    def feed(self, chunk: bytes) -> None: ...

    @abstractmethod
    def finalize(self) -> dict: ...


class ProviderAdapter(ABC):
    """Everything agentspy needs to know about a provider's protocol."""

    name: str = "?"

    @abstractmethod
    def is_model_call(self, path: str, body: dict | None) -> bool:
        """True if the request is a real call to the model (round trip).

        The proxy forwards ANY request; only those for which this method
        answers True are correlated and persisted as a round trip (e.g. for
        Anthropic it excludes /v1/messages/count_tokens).
        """

    @abstractmethod
    def analyze_request(self, body: dict) -> dict:
        """Educational summary of the request: model, system, tools, messages."""

    @abstractmethod
    def stream_collector(self) -> StreamCollector:
        """New collector for a streaming response."""

    @abstractmethod
    def json_response_summary(self, body: dict) -> dict:
        """Extracts usage/stop_reason from a non-streaming JSON response.

        Returns a dict (possibly empty) to be merged into the round trip's
        ``response`` record.
        """

    @abstractmethod
    def normalize_usage(self, usage: dict) -> dict:
        """Translates the wire usage into the neutral names of the DB columns.

        Expected output keys (all optional): ``input_tokens``,
        ``output_tokens``, ``cache_read_tokens``, ``cache_write_tokens`` and —
        for providers exposing the cache TTL — its split
        ``cache_write_5m_tokens`` / ``cache_write_1h_tokens`` (absent or None
        if the tier is unknown: they must not be flattened to 0).
        """
