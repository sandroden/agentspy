"""Inventario didattico degli elementi che compongono una richiesta all'LLM.

A partire dal `request.body` catturato dal proxy (system / tools / messages),
estrae la lista tipizzata di *artefatti* che entrano nel contesto: system
prompt, CLAUDE.md/MEMORY.md, immagini, file allegati via `@`, tools.

Non trasmette il contenuto: solo identità + dimensione. Vedi il piano in
`.claude/plans/` e i concept OKF (`token-accounting.md`).

Modulo a sé (nessun import da `proxy`/`store`) per restare riusabile e privo di
import circolari.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Marcatore con cui Claude Code inietta i file di istruzioni nel system-reminder
# del primo user message: `Contents of <path> (<descrizione>):`
_CONTENTS_RE = re.compile(r"Contents of (\S+) \(([^)]+)\):")

# Marcatore adiacente a un'immagine incollata: `[Image: source: <path>]`
_IMAGE_SOURCE_RE = re.compile(r"\[Image: source: ([^\]]+)\]")

# Blocco `role:"system"` con cui Claude Code pre-carica un `@file` come se fosse
# l'output di una Read (eager loading lato client; non è un vero tool_result).
_CALLED_TOOL_RE = re.compile(
    r'^Called the (\w+) tool with the following input: (\{.*?\})\s*\n'
    r'Result of calling the \w+ tool:\n',
    re.DOTALL,
)

_BILLING_PREFIX = "x-anthropic-billing-header:"

# Tool le cui `tool_result` iniettano nel contesto il *contenuto di un file*
# (identità = il path), non l'output di un comando. Un `@file` allegato
# dall'utente è lo stesso tipo di contenuto: differisce solo l'origine.
_FILE_READ_TOOLS = {"Read"}


def _jsize(obj: Any) -> int:
    """Dimensione in caratteri della serializzazione JSON (stima del peso)."""
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(obj))


def _block_text(block: Any) -> str:
    """Testo di un blocco messaggio (`{type:'text', text:...}`) o stringa."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict) and block.get("type") == "text":
        return block.get("text") or ""
    return ""


def _iter_message_blocks(messages: list[Any]):
    """Genera (role, block) per ogni blocco di ogni messaggio."""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "?")
        content = msg.get("content")
        if isinstance(content, str):
            yield role, {"type": "text", "text": content}
        elif isinstance(content, list):
            for block in content:
                yield role, block


def _claude_md_label(path: str, description: str) -> tuple[str, str]:
    """Restituisce (kind, label) per un marcatore `Contents of`."""
    desc = description.lower()
    if "auto-memory" in desc or path.endswith("MEMORY.md"):
        return "memory", "MEMORY.md"
    # CLAUDE.md globale vive sotto ~/.claude/, quello di progetto no.
    if "/.claude/CLAUDE.md" in path:
        return "claude-md", "CLAUDE.md (globale)"
    if path.endswith("CLAUDE.md"):
        return "claude-md", "CLAUDE.md (progetto)"
    # Altri file iniettati con lo stesso marcatore (es. MEMORY index).
    return "claude-md", path.rsplit("/", 1)[-1]


def _extract_system(system: Any) -> list[dict[str, Any]]:
    """Un artifact `system` sommando i blocchi, escluso il billing header.

    `system` può essere una lista di blocchi, una stringa o None.
    """
    if system is None:
        return []
    if isinstance(system, str):
        text = system
        return [{"kind": "system", "label": "System prompt", "chars": len(text)}] if text else []

    if not isinstance(system, list):
        return []

    texts: list[str] = []
    for block in system:
        text = _block_text(block)
        if text.startswith(_BILLING_PREFIX):
            continue  # header di billing, non fa parte del system prompt
        texts.append(text)

    # Fallback: se l'esclusione ha svuotato tutto (billing assente/formato
    # diverso), non azzerare mai il system prompt.
    if not texts:
        texts = [_block_text(b) for b in system]

    total = sum(len(t) for t in texts)
    if total == 0:
        return []
    return [{"kind": "system", "label": "System prompt", "chars": total}]


def _extract_instruction_files(messages: list[Any]) -> list[dict[str, Any]]:
    """CLAUDE.md/MEMORY.md dai marcatori `Contents of` nel system-reminder."""
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role, block in _iter_message_blocks(messages):
        text = _block_text(block)
        if "Contents of " not in text:
            continue
        for match in _CONTENTS_RE.finditer(text):
            path, description = match.group(1), match.group(2)
            if path in seen:
                continue
            seen.add(path)
            kind, label = _claude_md_label(path, description)
            artifacts.append(
                {
                    "kind": kind,
                    "label": label,
                    "path": path,
                    "description": description,
                }
            )
    return artifacts


def _extract_images(messages: list[Any]) -> list[dict[str, Any]]:
    """Un artifact per immagine base64 nei messages."""
    artifacts: list[dict[str, Any]] = []
    # Path sorgente disponibili dai marcatori adiacenti `[Image: source: X]`.
    sources: list[str] = []
    for _role, block in _iter_message_blocks(messages):
        for m in _IMAGE_SOURCE_RE.finditer(_block_text(block)):
            sources.append(m.group(1).strip())

    idx = 0
    for _role, block in _iter_message_blocks(messages):
        if not isinstance(block, dict) or block.get("type") != "image":
            continue
        source = block.get("source") or {}
        data = source.get("data") or ""
        path = sources[idx] if idx < len(sources) else None
        label = path.rsplit("/", 1)[-1] if path else "Immagine"
        artifacts.append(
            {
                "kind": "image",
                "label": label,
                "path": path,
                "media_type": source.get("media_type"),
                "chars": len(data) if isinstance(data, str) else _jsize(data),
            }
        )
        idx += 1
    return artifacts


def _extract_at_files(messages: list[Any]) -> list[dict[str, Any]]:
    """File pre-caricati via `@` — blocco `role:"system"` `Called the … tool`.

    Distinto dai veri tool_result (che hanno `role:"user"` e un `tool_use`
    agganciato): qui l'utente ha pre-allegato il file, l'LLM non ha deciso nulla.
    """
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role, block in _iter_message_blocks(messages):
        if role != "system":
            continue
        text = _block_text(block)
        match = _CALLED_TOOL_RE.match(text)
        if not match:
            continue
        tool, raw_input = match.group(1), match.group(2)
        try:
            file_path = (json.loads(raw_input) or {}).get("file_path")
        except (TypeError, ValueError):
            file_path = None
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        # chars = dimensione del contenuto iniettato (dopo l'header del marcatore)
        result = text[match.end():]
        artifacts.append(
            {
                "kind": "at-file",
                "label": "@" + file_path.rsplit("/", 1)[-1],
                "path": file_path,
                "description": f"pre-caricato via {tool}",
                "chars": len(result),
            }
        )
    return artifacts


def _content_len(content: Any) -> int:
    """Peso in caratteri del `content` di un tool_result (str o lista di blocchi)."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(_block_text(b)) for b in content)
    return _jsize(content)


def _extract_read_files(messages: list[Any]) -> list[dict[str, Any]]:
    """File caricati nel contesto da una `Read` decisa dall'LLM.

    A differenza di `_extract_at_files` (file pre-allegati dall'utente via `@`,
    blocco `role:"system"`), qui il modello ha chiesto la Read: nel body è un
    `tool_use` (role assistant) il cui `tool_result` (role user) trasporta il
    contenuto del file. Si correla `tool_result.tool_use_id → tool_use.input`
    per risalire al path. Stesso *contenuto* di un `@file`, diversa *origine*.

    Il chip compare nel round trip in cui il `tool_result` entra nel body (quello
    *successivo* alla Read), non in quello che emette il `tool_use`: prima di
    allora il file non è ancora nel contesto, c'è solo la richiesta di leggerlo.
    """
    # tool_use_id → (nome tool, input) raccolti dai messaggi assistant.
    uses: dict[str, tuple[str, dict[str, Any]]] = {}
    for _role, block in _iter_message_blocks(messages):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tid = block.get("id")
        if tid:
            uses[tid] = (block.get("name") or "", block.get("input") or {})

    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role, block in _iter_message_blocks(messages):
        if role != "user" or not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        name, tool_input = uses.get(block.get("tool_use_id"), ("", {}))
        if name not in _FILE_READ_TOOLS:
            continue
        file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        artifacts.append(
            {
                "kind": "read-file",
                "label": file_path.rsplit("/", 1)[-1],
                "path": file_path,
                "description": f"letto dall'agente via {name}",
                "chars": _content_len(block.get("content")),
            }
        )
    return artifacts


def _extract_tools(tools: Any) -> list[dict[str, Any]]:
    """Voce aggregata secondaria per i tool disponibili (già visibili altrove)."""
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
    """Inventario degli artefatti che compongono la richiesta `body`.

    Ritorna una lista di dict `{kind, label, path?, description?, chars?,
    count?, media_type?}`. Robusto a `body` non-dict o parziale.
    """
    if not isinstance(body, dict):
        return []
    messages = body.get("messages")
    messages = messages if isinstance(messages, list) else []

    artifacts: list[dict[str, Any]] = []
    artifacts += _extract_system(body.get("system"))
    artifacts += _extract_instruction_files(messages)
    artifacts += _extract_images(messages)
    artifacts += _extract_at_files(messages)
    artifacts += _extract_read_files(messages)
    artifacts += _extract_tools(body.get("tools"))
    return artifacts
