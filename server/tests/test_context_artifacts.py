import json

from agentspy_server.runtimes.claude_code_artifacts import (
    extract_artifact_content,
    extract_artifacts,
)

# Sample body reproducing the real cases observed in capture:
# billing header + system prompt, system-reminder with Contents of (2 CLAUDE.md +
# MEMORY.md), a pre-loaded @file (role:system), a pasted image with the
# [Image: source:] marker, a merely cited file (to ignore) and some tools.
SAMPLE_BODY = {
    "system": [
        {"type": "text", "text": "x-anthropic-billing-header: cc_version=2.1"},
        {"type": "text", "text": "You are Claude Code."},
        {"type": "text", "text": "A" * 1000},
    ],
    "tools": [{"name": "Bash"}, {"name": "Read"}, {"name": "Edit"}],
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "<system-reminder>\n"
                        "Contents of /home/u/.claude/CLAUDE.md (user's private global instructions):\n"
                        "global instructions\n"
                        "Contents of /home/u/proj/CLAUDE.md (project instructions):\n"
                        "project instructions\n"
                        "Contents of /home/u/.claude/memory/MEMORY.md (user's auto-memory):\n"
                        "memory\n"
                        "</system-reminder>"
                    ),
                },
                {"type": "text", "text": "Attaching @docs/style.md and citing docs/other.md"},
            ],
        },
        {
            "role": "system",
            "content": 'Called the Read tool with the following input: {"file_path":"docs/style.md"}\n'
            "Result of calling the Read tool:\n1\t.foo { color: red }\n",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Here is an image [Image #1]"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "Zm9v"}},
                {"type": "text", "text": "[Image: source: /home/u/.cache/1.png]"},
            ],
        },
        # The LLM decides on a Read (tool_use) and a Bash: only the first
        # brings file content into the context → a `read-file` artifact.
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_read1", "name": "Read", "input": {"file_path": "src/main.py"}},
                {"type": "tool_use", "id": "toolu_bash1", "name": "Bash", "input": {"command": "ls"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_read1", "content": "1\tprint('hi')\n"},
                {"type": "tool_result", "tool_use_id": "toolu_bash1", "content": "main.py\n"},
            ],
        },
    ],
}


def _by_kind(artifacts):
    out = {}
    for a in artifacts:
        out.setdefault(a["kind"], []).append(a)
    return out


def test_extract_covers_all_kinds():
    kinds = _by_kind(extract_artifacts(SAMPLE_BODY))
    assert set(kinds) == {"system", "claude-md", "memory", "image", "at-file", "read-file", "tools"}


def test_system_excludes_billing_header():
    system = _by_kind(extract_artifacts(SAMPLE_BODY))["system"][0]
    # 1000 chars of system prompt + "You are Claude Code." (20), NOT the billing header
    assert system["chars"] == 1000 + len("You are Claude Code.")


def test_instruction_files_labelled():
    kinds = _by_kind(extract_artifacts(SAMPLE_BODY))
    labels = {a["label"] for a in kinds["claude-md"]}
    assert labels == {"CLAUDE.md (global)", "CLAUDE.md (project)"}
    assert kinds["memory"][0]["path"].endswith("MEMORY.md")


def test_at_file_from_system_block_not_the_cited_one():
    at = _by_kind(extract_artifacts(SAMPLE_BODY))["at-file"]
    assert len(at) == 1
    assert at[0]["path"] == "docs/style.md"       # attached via @
    assert at[0]["chars"] > 0                      # injected content
    # the "merely cited" file (docs/other.md) must not show up
    assert all(a["path"] != "docs/other.md" for a in at)


def test_read_file_from_llm_tool_use():
    read = _by_kind(extract_artifacts(SAMPLE_BODY))["read-file"]
    assert len(read) == 1                          # only the Read, not the Bash
    assert read[0]["path"] == "src/main.py"        # path traced back via tool_use_id
    assert read[0]["label"] == "main.py"
    assert read[0]["chars"] == len("1\tprint('hi')\n")


def test_read_file_content_as_block_list():
    # `tool_result.content` can be a list of blocks, not only a string.
    body = {
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/a/b.txt"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": [{"type": "text", "text": "line one"}, {"type": "text", "text": "line two"}]},
            ]},
        ]
    }
    read = _by_kind(extract_artifacts(body))["read-file"]
    assert read[0]["chars"] == len("line one") + len("line two")


# Sample body reproducing reading a PDF via `@`: Claude Code does no eager
# loading (too large), the model calls Read in page ranges and the tool_result
# arrives with a textual stub + the pages as image blocks that are SIBLINGS of
# the tool_result (real case observed, event 2230/2232).
PDF_READ_BODY = {
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "in the file @man.pdf ..."}]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Read",
             "input": {"file_path": "/docs/man.pdf", "pages": "1-6"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "PDF pages extracted: 6 page(s)"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "A" * 100}},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "B" * 200}},
        ]},
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t2", "name": "Read",
             "input": {"file_path": "/docs/man.pdf", "pages": "7-13"}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "PDF pages extracted: 7 page(s)"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "C" * 300}},
        ]},
    ]
}


def test_file_ref_from_too_large_pdf_notice():
    # `@file` too large for eager loading: Claude Code injects only a
    # role:system notice → `file-ref` artifact (referenced, not loaded).
    notice = (
        "PDF file: /docs/man.pdf (13 pages, 1.4MB). This PDF is too large to read "
        'all at once. You MUST use the Read tool with the pages parameter to read '
        'specific page ranges (e.g., pages: "1-5"). Maximum 20 pages per request.'
    )
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "in the file @man.pdf ..."}]},
            # in the real case the notice shares the system block with other
            # notifications (deferred tools): only the first paragraph weighs
            {"role": "system", "content": notice + "\n\nThe following deferred tools are now available..."},
        ]
    }
    kinds = _by_kind(extract_artifacts(body))
    assert "at-file" not in kinds                  # no pre-loaded content
    ref = kinds["file-ref"][0]
    assert ref["path"] == "/docs/man.pdf"
    assert ref["label"] == "@man.pdf"
    assert "not loaded" in ref["description"]
    assert ref["chars"] == len(notice)             # only the notice, not the rest of the block


def test_tool_result_images_are_not_user_images():
    # The PDF pages (image siblings of a tool_result) are NOT user
    # attachments: no `image` artifact, no phantom YOU bubble.
    kinds = _by_kind(extract_artifacts(PDF_READ_BODY))
    assert "image" not in kinds


def test_read_file_weighs_sibling_images_and_accumulates():
    read = _by_kind(extract_artifacts(PDF_READ_BODY))["read-file"]
    # Repeated reads of the same path → a single artifact, weights summed.
    assert len(read) == 1
    assert read[0]["path"] == "/docs/man.pdf"
    expected = (
        len("PDF pages extracted: 6 page(s)") + 100 + 200
        + len("PDF pages extracted: 7 page(s)") + 300
    )
    assert read[0]["chars"] == expected


def test_read_file_counts_images_inside_tool_result_content():
    # Images INSIDE `tool_result.content` (e.g. screenshots): counted in the weight.
    body = {
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/a/shot.png"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "D" * 50}},
                ]},
            ]},
        ]
    }
    read = _by_kind(extract_artifacts(body))["read-file"]
    assert read[0]["chars"] == len("ok") + 50


def test_image_has_source_path():
    img = _by_kind(extract_artifacts(SAMPLE_BODY))["image"][0]
    assert img["path"] == "/home/u/.cache/1.png"
    assert img["media_type"] == "image/png"


def test_tools_aggregate():
    tools = _by_kind(extract_artifacts(SAMPLE_BODY))["tools"][0]
    assert tools["count"] == 3


def test_robust_to_degenerate_bodies():
    assert extract_artifacts(None) == []
    assert extract_artifacts({}) == []
    # system:null (token-count calls) → no system artifact, no error
    assert extract_artifacts({"system": None, "messages": []}) == []
    # system as a string
    out = extract_artifacts({"system": "whole prompt"})
    assert out and out[0]["kind"] == "system"


def test_system_fallback_when_no_billing_block():
    # if the billing header is missing, never zero out the system prompt
    body = {"system": [{"type": "text", "text": "You are a security monitor."}]}
    out = extract_artifacts(body)
    assert out[0]["kind"] == "system"
    assert out[0]["chars"] == len("You are a security monitor.")


# -- content on demand (artifact reader) -------------------------------------


def test_content_system_joins_blocks_without_billing():
    item = extract_artifact_content(SAMPLE_BODY, "system|System prompt")
    assert item["format"] == "markdown"
    # the weight is not repeated here: it has one definition, the inventory's
    assert "chars" not in item
    assert item["content"].startswith("You are Claude Code.")
    assert "billing" not in item["content"]


def test_content_instruction_file_stops_at_next_marker():
    item = extract_artifact_content(SAMPLE_BODY, "claude-md|/home/u/proj/CLAUDE.md")
    assert item["content"] == "project instructions"
    assert item["label"] == "CLAUDE.md"
    mem = extract_artifact_content(SAMPLE_BODY, "memory|/home/u/.claude/memory/MEMORY.md")
    # last marker of the block: runs to the end of the reminder
    assert mem["content"].startswith("memory")


def test_content_at_file_is_the_preloaded_body():
    item = extract_artifact_content(SAMPLE_BODY, "at-file|docs/style.md")
    assert item["content"] == "1\t.foo { color: red }\n"
    assert item["format"] == "markdown"   # .md → renderable


def test_content_read_file_concatenates_repeated_reads():
    item = extract_artifact_content(PDF_READ_BODY, "read-file|/docs/man.pdf")
    assert item["content"].count("PDF pages extracted") == 2
    # the images sibling of the tool_result are the content of the file
    assert len(item["images"]) == 3
    assert item["images"][0].startswith("data:image/jpeg;base64,")


def test_content_image_returns_data_uri():
    item = extract_artifact_content(SAMPLE_BODY, "image|/home/u/.cache/1.png")
    assert item["format"] == "image"
    assert item["images"] == ["data:image/png;base64,Zm9v"]


def test_content_tools_is_pretty_json():
    item = extract_artifact_content(SAMPLE_BODY, "tools|Tools (3)")
    assert item["format"] == "json"
    assert json.loads(item["content"])[0]["name"] == "Bash"


def test_content_missing_or_degenerate():
    assert extract_artifact_content(SAMPLE_BODY, "claude-md|/nope/CLAUDE.md") is None
    assert extract_artifact_content(SAMPLE_BODY, "bogus-kind|x") is None
    assert extract_artifact_content(SAMPLE_BODY, "no-separator") is None
    assert extract_artifact_content(None, "system|System prompt") is None
