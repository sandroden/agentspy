"""Educational inventory of the elements making up a request to the LLM.

Implementation detail of the Claude Code runtime (exposed via
``ClaudeCodeRuntime.extract_artifacts``): the way Claude Code injects
instructions and attachments into the context — the "Contents of…", "Called the
X tool" markers, the notices about files that are too large — is its own
knowledge.

Starting from the `request.body` captured by the proxy (system / tools /
messages), it extracts the typed list of *artifacts* entering the context:
system prompt, CLAUDE.md/MEMORY.md, images, files attached via `@`, tools.

The inventory does not transmit the content: only identity + size (it is
computed for every round trip of a session, it must stay light). The content of
a *single* artifact is retrieved on demand with ``extract_artifact_content``,
which re-reads the body looking only for the requested one. See the plan in
`.claude/plans/` and the OKF concepts (`token-accounting.md`).

Standalone module (no import from `proxy`/`store`) to stay reusable and free of
circular imports.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Marker with which Claude Code injects the instruction files into the
# system-reminder of the first user message: `Contents of <path> (<description>):`
_CONTENTS_RE = re.compile(r"Contents of (\S+) \(([^)]+)\):")

# Marker adjacent to a pasted image: `[Image: source: <path>]`
_IMAGE_SOURCE_RE = re.compile(r"\[Image: source: ([^\]]+)\]")

# `role:"system"` block with which Claude Code preloads an `@file` as if it were
# the output of a Read (client-side eager loading; not a real tool_result).
_CALLED_TOOL_RE = re.compile(
    r'^Called the (\w+) tool with the following input: (\{.*?\})\s*\n'
    r'Result of calling the \w+ tool:\n',
    re.DOTALL,
)

# `role:"system"` notice with which Claude Code flags an `@file` too large for
# eager loading (observed with PDFs): the file is only *referenced*, the content
# is NOT in the context until the model reads it with Read.
_FILE_REF_RE = re.compile(r"^PDF file: (\S+) \(([^)]+)\)\. This PDF is too large")

_BILLING_PREFIX = "x-anthropic-billing-header:"

# Tools whose `tool_result` injects into the context the *content of a file*
# (identity = the path), not the output of a command. An `@file` attached by the
# user is the same kind of content: only the origin differs.
_FILE_READ_TOOLS = {"Read"}


def _jsize(obj: Any) -> int:
    """Size in characters of the JSON serialization (weight estimate)."""
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except (TypeError, ValueError):
        return len(str(obj))


def _block_text(block: Any) -> str:
    """Text of a message block (`{type:'text', text:...}`) or string."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict) and block.get("type") == "text":
        return block.get("text") or ""
    return ""


def _iter_message_blocks(messages: list[Any]):
    """Yields (role, block) for every block of every message."""
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
    """Returns (kind, label) for a `Contents of` marker."""
    desc = description.lower()
    if "auto-memory" in desc or path.endswith("MEMORY.md"):
        return "memory", "MEMORY.md"
    # The global CLAUDE.md lives under ~/.claude/, the project one does not.
    if "/.claude/CLAUDE.md" in path:
        return "claude-md", "CLAUDE.md (global)"
    if path.endswith("CLAUDE.md"):
        return "claude-md", "CLAUDE.md (project)"
    # Other files injected with the same marker (e.g. MEMORY index).
    return "claude-md", path.rsplit("/", 1)[-1]


def _extract_system(system: Any) -> list[dict[str, Any]]:
    """One `system` artifact summing the blocks, billing header excluded.

    `system` may be a list of blocks, a string or None.
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
            continue  # billing header, not part of the system prompt
        texts.append(text)

    # Fallback: if the exclusion emptied everything (billing absent/different
    # format), never zero out the system prompt.
    if not texts:
        texts = [_block_text(b) for b in system]

    total = sum(len(t) for t in texts)
    if total == 0:
        return []
    return [{"kind": "system", "label": "System prompt", "chars": total}]


def _extract_instruction_files(messages: list[Any]) -> list[dict[str, Any]]:
    """CLAUDE.md/MEMORY.md from the `Contents of` markers in the system-reminder."""
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


def _message_blocks(msg: Any) -> list[Any]:
    """The content blocks of a message (str normalised to a text block)."""
    if not isinstance(msg, dict):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def _has_tool_result(blocks: list[Any]) -> bool:
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)


def _image_weight(block: dict[str, Any]) -> int:
    """Weight in characters of an image block (length of the base64)."""
    data = (block.get("source") or {}).get("data") or ""
    return len(data) if isinstance(data, str) else _jsize(data)


def _extract_images(messages: list[Any]) -> list[dict[str, Any]]:
    """One artifact per image pasted by the user in the messages.

    Images living in a message with a `tool_result` are tool output (e.g. PDF
    pages rendered by a Read), not user attachments: they are skipped here and
    their weight is attributed to the `read-file` artifact in
    `_extract_read_files`.
    """
    # Only messages without a tool_result carry pasted images.
    eligible = [_message_blocks(m) for m in messages]
    eligible = [blocks for blocks in eligible if blocks and not _has_tool_result(blocks)]

    # Source paths available from the adjacent `[Image: source: X]` markers.
    sources: list[str] = []
    for blocks in eligible:
        for block in blocks:
            for m in _IMAGE_SOURCE_RE.finditer(_block_text(block)):
                sources.append(m.group(1).strip())

    artifacts: list[dict[str, Any]] = []
    idx = 0
    for blocks in eligible:
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            path = sources[idx] if idx < len(sources) else None
            label = path.rsplit("/", 1)[-1] if path else "Image"
            artifacts.append(
                {
                    "kind": "image",
                    "label": label,
                    "path": path,
                    "media_type": (block.get("source") or {}).get("media_type"),
                    "chars": _image_weight(block),
                }
            )
            idx += 1
    return artifacts


def _extract_at_files(messages: list[Any]) -> list[dict[str, Any]]:
    """Files preloaded via `@` — `role:"system"` block `Called the … tool`.

    Distinct from real tool_results (which have `role:"user"` and an attached
    `tool_use`): here the user pre-attached the file, the LLM decided nothing.
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
        # chars = size of the injected content (after the marker header)
        result = text[match.end():]
        artifacts.append(
            {
                "kind": "at-file",
                "label": "@" + file_path.rsplit("/", 1)[-1],
                "path": file_path,
                "description": f"pre-loaded via {tool}",
                "chars": len(result),
            }
        )
    return artifacts


def _extract_file_refs(messages: list[Any]) -> list[dict[str, Any]]:
    """Files attached via `@` but only *referenced* (content not loaded).

    When the `@file` is too large for eager loading (observed with PDFs),
    Claude Code injects a `role:"system"` notice ("PDF file: <path> … too
    large … use the Read tool") instead of the content. It is still a user
    attachment — it differs from `at-file` because only the notice enters the
    context (a few hundred chars), not the file: that will arrive, if the model
    decides to read it, as a `read-file`.
    """
    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role, block in _iter_message_blocks(messages):
        if role != "system":
            continue
        text = _block_text(block)
        match = _FILE_REF_RE.match(text)
        if not match:
            continue
        file_path, info = match.group(1), match.group(2)
        if file_path in seen:
            continue
        seen.add(file_path)
        # Only the notice weighs on the context (first paragraph of the system block).
        notice = text.split("\n\n", 1)[0]
        artifacts.append(
            {
                "kind": "file-ref",
                "label": "@" + file_path.rsplit("/", 1)[-1],
                "path": file_path,
                "description": f"referenced via @ ({info}) — content not loaded",
                "chars": len(notice),
            }
        )
    return artifacts


def _content_len(content: Any) -> int:
    """Weight in characters of a tool_result `content` (str or list of blocks)."""
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


def _extract_read_files(messages: list[Any]) -> list[dict[str, Any]]:
    """Files loaded into the context by a `Read` decided by the LLM.

    Unlike `_extract_at_files` (files pre-attached by the user via `@`,
    `role:"system"` block), here the model asked for the Read: in the body it is
    a `tool_use` (role assistant) whose `tool_result` (role user) carries the
    file content. `tool_result.tool_use_id → tool_use.input` is correlated to
    get back to the path. Same *content* as an `@file`, different *origin*.

    The chip shows up in the round trip where the `tool_result` enters the body
    (the one *after* the Read), not in the one emitting the `tool_use`: before
    then the file is not in the context yet, there is only the request to read it.
    """
    # tool_use_id → (tool name, input) collected from the assistant messages.
    uses: dict[str, tuple[str, dict[str, Any]]] = {}
    for _role, block in _iter_message_blocks(messages):
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tid = block.get("id")
        if tid:
            uses[tid] = (block.get("name") or "", block.get("input") or {})

    artifacts: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        blocks = _message_blocks(msg)
        # Images sibling to the tool_result in the same message: they are the
        # content of the file read (e.g. PDF pages rendered as JPEG by Read), so
        # they weigh on the read-file artifact, not as "image".
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
            file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
            if not file_path:
                continue
            chars = _content_len(block.get("content"))
            existing = by_path.get(file_path)
            if existing is None:
                existing = {
                    "kind": "read-file",
                    "label": file_path.rsplit("/", 1)[-1],
                    "path": file_path,
                    "description": f"read by the agent via {name}",
                    "chars": chars,
                }
                by_path[file_path] = existing
                artifacts.append(existing)
            else:
                # Repeated reads of the same file (e.g. PDF in page chunks):
                # a single artifact, weights summed.
                existing["chars"] += chars
            msg_artifacts.append(existing)
        if sibling_images and len(msg_artifacts) == 1:
            msg_artifacts[0]["chars"] += sibling_images
    return artifacts


def _extract_tools(tools: Any) -> list[dict[str, Any]]:
    """Secondary aggregate entry for the available tools (already visible elsewhere)."""
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


def _data_uri(block: dict[str, Any]) -> str:
    """`data:` URI of an image block, ready for an `<img src>`."""
    source = block.get("source") or {}
    media_type = source.get("media_type") or "image/png"
    data = source.get("data") or ""
    return f"data:{media_type};base64,{data}"


def _content_system(system: Any) -> str | None:
    """Text of the system prompt (billing header excluded), as sent."""
    if isinstance(system, str):
        return system or None
    if not isinstance(system, list):
        return None
    texts = [t for t in (_block_text(b) for b in system) if not t.startswith(_BILLING_PREFIX)]
    if not texts:
        texts = [_block_text(b) for b in system]
    joined = "\n\n".join(t for t in texts if t)
    return joined or None


def _content_instruction_file(messages: list[Any], path: str) -> str | None:
    """Body of a `Contents of <path> (...)` marker: everything up to the next
    marker (Claude Code concatenates several instruction files in one block)."""
    for _role, block in _iter_message_blocks(messages):
        text = _block_text(block)
        if "Contents of " not in text:
            continue
        matches = list(_CONTENTS_RE.finditer(text))
        for i, match in enumerate(matches):
            if match.group(1) != path:
                continue
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return text[match.end():end].strip("\n")
    return None


def _content_at_file(messages: list[Any], path: str) -> str | None:
    """Content injected by the eager loading of an `@file`."""
    for role, block in _iter_message_blocks(messages):
        if role != "system":
            continue
        text = _block_text(block)
        match = _CALLED_TOOL_RE.match(text)
        if not match:
            continue
        try:
            file_path = (json.loads(match.group(2)) or {}).get("file_path")
        except (TypeError, ValueError):
            file_path = None
        if file_path == path:
            return text[match.end():]
    return None


def _content_file_ref(messages: list[Any], path: str) -> str | None:
    """The notice (that is the only thing that entered the context) of a referenced `@file`."""
    for role, block in _iter_message_blocks(messages):
        if role != "system":
            continue
        text = _block_text(block)
        match = _FILE_REF_RE.match(text)
        if match and match.group(1) == path:
            return text.split("\n\n", 1)[0]
    return None


def _content_read_file(messages: list[Any], path: str) -> tuple[str | None, list[str]]:
    """Text (and images) of the `tool_result`s of the Reads on `path`.

    Repeated reads of the same file are concatenated in body order, as they
    weigh on the context: same criterion as the `chars` of the inventory.
    """
    uses: dict[str, tuple[str, dict[str, Any]]] = {}
    for _role, block in _iter_message_blocks(messages):
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
            uses[block["id"]] = (block.get("name") or "", block.get("input") or {})

    chunks: list[str] = []
    images: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        blocks = _message_blocks(msg)
        hit = False
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            name, tool_input = uses.get(block.get("tool_use_id"), ("", {}))
            if name not in _FILE_READ_TOOLS:
                continue
            if not isinstance(tool_input, dict) or tool_input.get("file_path") != path:
                continue
            hit = True
            content = block.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "image":
                        images.append(_data_uri(b))
                    else:
                        chunks.append(_block_text(b))
        if hit:
            # Images sibling to the tool_result are the content of the file
            # (e.g. PDF pages rendered by Read), not separate attachments.
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "image":
                    images.append(_data_uri(block))
    text = "\n\n".join(c for c in chunks if c)
    return (text or None), images


def _content_image(messages: list[Any], ident: str) -> tuple[str | None, str | None]:
    """(data URI, media_type) of a pasted image, found by source path or label."""
    eligible = [_message_blocks(m) for m in messages]
    eligible = [blocks for blocks in eligible if blocks and not _has_tool_result(blocks)]
    sources: list[str] = []
    for blocks in eligible:
        for block in blocks:
            for m in _IMAGE_SOURCE_RE.finditer(_block_text(block)):
                sources.append(m.group(1).strip())

    idx = 0
    for blocks in eligible:
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "image":
                continue
            path = sources[idx] if idx < len(sources) else None
            label = path.rsplit("/", 1)[-1] if path else "Image"
            idx += 1
            if ident in (path, label):
                return _data_uri(block), (block.get("source") or {}).get("media_type")
    return None, None


def _format_for(kind: str, path: str | None) -> str:
    """Rendering hint for the UI: markdown / json / image / text."""
    if kind == "image":
        return "image"
    if kind == "tools":
        return "json"
    if kind in ("system", "claude-md", "memory"):
        return "markdown"
    if path and path.rsplit(".", 1)[-1].lower() in ("md", "markdown"):
        return "markdown"
    return "text"


def extract_artifact_content(body: Any, key: str) -> dict[str, Any] | None:
    """Content of a *single* artifact of `body`, identified by `key`.

    `key` is `"{kind}|{path or label}"` — the same identity the UI uses to
    recognise an artifact across round trips (`artifactKey` in the frontend).

    Returns `{kind, label, path, media_type, format, content, images}` or None
    if the artifact is not in this body. `content` is the text as it entered the
    context; `images` holds the `data:` URIs when the content is graphical.

    Deliberately no `chars`: the weight has a single definition, the inventory's
    (`extract_artifacts`), which the UI already has in hand — two counts of the
    same thing would drift.
    """
    if not isinstance(body, dict) or "|" not in key:
        return None
    kind, ident = key.split("|", 1)
    messages = body.get("messages")
    messages = messages if isinstance(messages, list) else []

    path: str | None = None
    content: str | None = None
    images: list[str] = []
    label = ident
    media_type: str | None = None

    if kind == "system":
        content = _content_system(body.get("system"))
        path, label = None, "System prompt"
    elif kind in ("claude-md", "memory"):
        content = _content_instruction_file(messages, ident)
        path = ident
        label = ident.rsplit("/", 1)[-1]
    elif kind == "at-file":
        content = _content_at_file(messages, ident)
        path = ident
        label = "@" + ident.rsplit("/", 1)[-1]
    elif kind == "file-ref":
        content = _content_file_ref(messages, ident)
        path = ident
        label = "@" + ident.rsplit("/", 1)[-1]
    elif kind == "read-file":
        content, images = _content_read_file(messages, ident)
        path = ident
        label = ident.rsplit("/", 1)[-1]
    elif kind == "image":
        uri, media_type = _content_image(messages, ident)
        if uri:
            images = [uri]
        label = ident.rsplit("/", 1)[-1]
    elif kind == "tools":
        tools = body.get("tools")
        if isinstance(tools, list) and tools:
            content = json.dumps(tools, ensure_ascii=False, indent=2)
            label = f"Tools ({len(tools)})"
        path = None
    else:
        return None

    if content is None and not images:
        return None
    return {
        "kind": kind,
        "label": label,
        "path": path,
        "media_type": media_type,
        "format": _format_for(kind, path),
        "content": content,
        "images": images,
    }


def extract_artifacts(body: Any) -> list[dict[str, Any]]:
    """Inventory of the artifacts making up the `body` request.

    Returns a list of dicts `{kind, label, path?, description?, chars?,
    count?, media_type?}`. Robust to a non-dict or partial `body`.
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
    artifacts += _extract_file_refs(messages)
    artifacts += _extract_read_files(messages)
    artifacts += _extract_tools(body.get("tools"))
    return artifacts
