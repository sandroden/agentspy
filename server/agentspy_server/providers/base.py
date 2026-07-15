"""Strato provider: isola il protocollo wire del provider LLM.

agentspy persiste e renderizza un modello interno "neutro" che è
deliberatamente derivato dalla Messages API di Anthropic:

- la risposta ricostruita è un ``message`` con ``content`` a blocchi tipati
  (``text``, ``thinking``, ``tool_use``, ``tool_result``, ``image``);
- l'usage nelle colonne DB usa nomi neutri (``input_tokens``,
  ``output_tokens``, ``cache_read_tokens``, ``cache_write_tokens``).

Un adapter per un altro provider (es. OpenAI Responses API) deve TRADURRE il
proprio wire format in questo modello al momento dell'ingest: per Anthropic
la traduzione è (quasi) l'identità, quindi i payload già salvati restano
validi senza migrazione. Il body grezzo della richiesta resta persistito
così com'è passato sul filo — è il materiale didattico — mentre tutto ciò
che il resto del sistema *interpreta* (round trip sì/no, analysis, blocchi
della risposta, usage) passa da questa interfaccia.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StreamCollector(ABC):
    """Ricostruisce la risposta del modello da uno stream di byte (es. SSE).

    ``finalize()`` deve restituire un dict nel modello neutro:
    ``{"type": ..., "message": {..., "content": [blocchi]}, "usage": {...},
    "stop_reason": ..., "events_count": {...}}`` più ``"error"`` opzionale.
    ``usage`` può usare i nomi wire del provider: la traduzione nei nomi
    neutri avviene con ``ProviderAdapter.normalize_usage``.
    """

    @abstractmethod
    def feed(self, chunk: bytes) -> None: ...

    @abstractmethod
    def finalize(self) -> dict: ...


class ProviderAdapter(ABC):
    """Tutto ciò che agentspy deve sapere del protocollo di un provider."""

    name: str = "?"

    @abstractmethod
    def is_model_call(self, path: str, body: dict | None) -> bool:
        """True se la richiesta è una vera chiamata al modello (round trip).

        Il proxy inoltra QUALUNQUE richiesta; solo quelle per cui questo
        metodo risponde True vengono correlate e persistite come round trip
        (es. per Anthropic esclude /v1/messages/count_tokens).
        """

    @abstractmethod
    def analyze_request(self, body: dict) -> dict:
        """Sintesi didattica della richiesta: model, system, tools, messages."""

    @abstractmethod
    def stream_collector(self) -> StreamCollector:
        """Nuovo collector per una risposta in streaming."""

    @abstractmethod
    def json_response_summary(self, body: dict) -> dict:
        """Estrae usage/stop_reason da una risposta JSON non in streaming.

        Ritorna un dict (eventualmente vuoto) da fondere nel record
        ``response`` del round trip.
        """

    @abstractmethod
    def normalize_usage(self, usage: dict) -> dict:
        """Traduce l'usage wire nei nomi neutri delle colonne DB.

        Chiavi attese in output (tutte opzionali): ``input_tokens``,
        ``output_tokens``, ``cache_read_tokens``, ``cache_write_tokens``.
        """
