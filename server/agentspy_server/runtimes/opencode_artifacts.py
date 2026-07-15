"""Inventario didattico degli artefatti di una richiesta generata da opencode.

Dettaglio implementativo di ``OpencodeRuntime.extract_artifacts``. La *meccanica*
(pesare immagini, correlare tool_use→tool_result) è la stessa di Claude Code —
il wire è identico, formato Messages API di Anthropic — ma i *marcatori* con cui
opencode inietta le istruzioni nel contesto sono diversi e vivono in un posto
diverso, quindi questo modulo è autonomo (nessun import da
``claude_code_artifacts``) per non accoppiare i due runtime.

Differenze rispetto a Claude Code:
- opencode inietta i file di istruzioni (AGENTS.md/CLAUDE.md) come blocchi del
  **system prompt**, ciascuno col prefisso letterale ``Instructions from: <path>``
  (Claude Code li mette nel system-reminder del primo messaggio user come
  ``Contents of <path>``);
- non c'è header di billing nel system, né eager-loading di ``@file``
  (``role:"system"`` "Called the … tool"), né marcatori ``[Image: source:]``;
- i tool su file hanno nomi minuscoli (``read``) e il path è nel campo
  ``filePath``.
"""

from __future__ import annotations

import json
import re
from typing import Any

# opencode antepone a ogni file di istruzioni questo prefisso, una riga per
# file, dentro il system prompt (session/instruction.py, funzione system()).
_INSTRUCTIONS_RE = re.compile(r"^Instructions from: (\S+)", re.MULTILINE)

# Il system osservato sulla wire (opencode 1.18) è UN blocco unico: prompt base,
# poi i file di istruzioni ("Instructions from: <path>\n<contenuto>"), poi altre
# sezioni (skills, mcp, references) concatenate SENZA delimitatore di chiusura
# delle istruzioni. Il contenuto di un file può contenere righe vuote, quindi lo
# span di un file termina al prossimo marcatore di istruzioni O al primo incipit
# di sezione nota. Incipit verificati sul bundle di opencode 1.18 (SystemPrompt
# .skills/.mcp, ReferenceGuidance): fragili per costruzione, da riverificare a
# ogni major di opencode.
_SECTION_OPENERS_RE = re.compile(
    r"^(?:Skills provide specialized instructions"
    r"|<mcp_instructions>"
    r"|Project references provide additional directories"
    r"|<available_references>)",
    re.MULTILINE,
)

# Tool le cui tool_result iniettano nel contesto il *contenuto di un file*.
_FILE_READ_TOOLS = {"read"}
# Campo dello schema del tool `read` che porta il path (opencode usa camelCase
# ``filePath``; si accettano varianti per robustezza a differenze di versione).
_READ_PATH_KEYS = ("filePath", "file_path", "path")


def _jsize(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(obj))


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict) and block.get("type") == "text":
        return block.get("text") or ""
    return ""


def _message_blocks(msg: Any) -> list[Any]:
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def _has_tool_result(blocks: list[Any]) -> bool:
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)


def _image_weight(block: dict[str, Any]) -> int:
    data = (block.get("source") or {}).get("data") or ""
    return len(data) if isinstance(data, str) else _jsize(data)


def _content_len(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for b in content:
            if isinstance(b, dict) and b.get("type") == "image":
                total += _image_weight(b)
            else:
                total += len(_block_text(b))
        return total
    return _jsize(content)


def _instruction_label(path: str) -> tuple[str, str]:
    """(kind, label) per un file di istruzioni iniettato da opencode.

    Si riusa il kind generico ``claude-md`` (istruzioni di progetto/globali) già
    reso dal frontend; il label è il nome del file, che distingue AGENTS.md da
    CLAUDE.md."""
    return "claude-md", path.rsplit("/", 1)[-1]


def _instruction_spans(text: str) -> list[tuple[str, int, int]]:
    """Span ``(path, start, end)`` dei file di istruzioni dentro un testo system.

    ``end`` è il minimo fra il prossimo marcatore ``Instructions from:`` e il
    primo incipit di sezione nota (vedi ``_SECTION_OPENERS_RE``): il contenuto
    di un file può contenere righe vuote, quindi non ci si può fermare alla
    prima riga vuota."""
    matches = list(_INSTRUCTIONS_RE.finditer(text))
    spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        hard_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        boundary = _SECTION_OPENERS_RE.search(text, m.end(), hard_end)
        spans.append((m.group(1), m.start(), boundary.start() if boundary else hard_end))
    return spans


def _split_system_text(
    text: str, by_path: dict[str, dict[str, Any]], order: list[dict[str, Any]]
) -> int:
    """Scorpora i file di istruzioni da un testo system; ritorna i chars residui.

    Gli artefatti confluiscono in ``by_path``/``order`` (condivisi fra più
    blocchi): letture ripetute dello stesso path sommano i pesi in un unico
    artefatto invece di duplicarlo."""
    instr_chars = 0
    for path, start, end in _instruction_spans(text):
        span = end - start
        instr_chars += span
        art = by_path.get(path)
        if art is None:
            kind, label = _instruction_label(path)
            art = {"kind": kind, "label": label, "path": path, "chars": 0}
            by_path[path] = art
            order.append(art)
        art["chars"] += span
    return len(text) - instr_chars


def _extract_system_and_instructions(system: Any) -> list[dict[str, Any]]:
    """System prompt + file di istruzioni scorporati, in modo NON additivo.

    Il peso degli span ``Instructions from:`` è sottratto dal totale del system
    prompt e attribuito a un artefatto per file: così la somma dei chip riflette
    la reale composizione del contesto, senza doppio conteggio.

    Vale sia per il system in **stringa** sia in **lista** di blocchi: sulla
    wire osservata (opencode 1.18) il system è un unico blocco che concatena
    prompt base, istruzioni e sezioni successive, quindi anche nel caso lista
    ogni blocco va scorporato per span, non classificato per intero.
    """
    blocks: list[str]
    if isinstance(system, str):
        blocks = [system]
    elif isinstance(system, list):
        blocks = [_block_text(b) for b in system]
    else:
        return []

    system_chars = 0
    by_path: dict[str, dict[str, Any]] = {}
    order: list[dict[str, Any]] = []
    for text in blocks:
        system_chars += _split_system_text(text, by_path, order)

    result: list[dict[str, Any]] = []
    if system_chars > 0:
        result.append({"kind": "system", "label": "System prompt", "chars": system_chars})
    result.extend(order)
    return result


def _extract_images(messages: list[Any]) -> list[dict[str, Any]]:
    """Un artifact per immagine incollata dall'utente.

    Come in Claude Code, le immagini fratelle di un ``tool_result`` sono output
    di tool (contenuto di un file letto) e vanno pesate sul ``read-file``, non
    qui: si considerano solo i messaggi senza tool_result. opencode non affianca
    marcatori col path sorgente, quindi il label è generico."""
    artifacts: list[dict[str, Any]] = []
    for msg in messages:
        blocks = _message_blocks(msg)
        if not blocks or _has_tool_result(blocks):
            continue
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            artifacts.append(
                {
                    "kind": "image",
                    "label": "Immagine",
                    "path": None,
                    "media_type": (block.get("source") or {}).get("media_type"),
                    "chars": _image_weight(block),
                }
            )
    return artifacts


def _read_path(tool_input: Any) -> str | None:
    if not isinstance(tool_input, dict):
        return None
    for key in _READ_PATH_KEYS:
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _extract_read_files(messages: list[Any]) -> list[dict[str, Any]]:
    """File caricati nel contesto da una ``read`` decisa dall'LLM.

    Correla ``tool_result.tool_use_id → tool_use.input`` per risalire al path;
    letture ripetute dello stesso file confluiscono in un artefatto coi pesi
    sommati. Immagini fratelle del tool_result (es. pagine renderizzate) pesano
    su questo artefatto."""
    uses: dict[str, tuple[str, dict[str, Any]]] = {}
    for msg in messages:
        for block in _message_blocks(msg):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                uses[block["id"]] = (block.get("name") or "", block.get("input") or {})

    artifacts: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        blocks = _message_blocks(msg)
        sibling_images = 0
        msg_artifacts: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "image":
                sibling_images += _image_weight(block)
                continue
            if block.get("type") != "tool_result":
                continue
            name, tool_input = uses.get(block.get("tool_use_id"), ("", {}))
            if name not in _FILE_READ_TOOLS:
                continue
            file_path = _read_path(tool_input)
            if not file_path:
                continue
            chars = _content_len(block.get("content"))
            existing = by_path.get(file_path)
            if existing is None:
                existing = {
                    "kind": "read-file",
                    "label": file_path.rsplit("/", 1)[-1],
                    "path": file_path,
                    "description": f"letto dall'agente via {name}",
                    "chars": chars,
                }
                by_path[file_path] = existing
                artifacts.append(existing)
            else:
                existing["chars"] += chars
            msg_artifacts.append(existing)
        if sibling_images and len(msg_artifacts) == 1:
            msg_artifacts[0]["chars"] += sibling_images
    return artifacts


def _extract_tools(tools: Any) -> list[dict[str, Any]]:
    if not tools or not isinstance(tools, list):
        return []
    return [
        {
            "kind": "tools",
            "label": f"Tools ({len(tools)})",
            "count": len(tools),
            "chars": _jsize(tools),
        }
    ]


def extract_artifacts(body: Any) -> list[dict[str, Any]]:
    """Inventario degli artefatti che compongono la richiesta ``body``.

    Robusto a ``body`` non-dict o parziale. Vedi il gemello di Claude Code in
    ``claude_code_artifacts.extract_artifacts``."""
    if not isinstance(body, dict):
        return []
    messages = body.get("messages")
    messages = messages if isinstance(messages, list) else []

    artifacts: list[dict[str, Any]] = []
    artifacts += _extract_system_and_instructions(body.get("system"))
    artifacts += _extract_images(messages)
    artifacts += _extract_read_files(messages)
    artifacts += _extract_tools(body.get("tools"))
    return artifacts
