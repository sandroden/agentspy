from agentspy_server.context_artifacts import extract_artifacts

# Body campione che riproduce i casi reali osservati in cattura:
# billing header + system prompt, system-reminder con Contents of (2 CLAUDE.md +
# MEMORY.md), un @file pre-caricato (role:system), un'immagine incollata con
# marcatore [Image: source:], un file solo citato (da ignorare) e dei tools.
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
                        "istruzioni globali\n"
                        "Contents of /home/u/proj/CLAUDE.md (project instructions):\n"
                        "istruzioni progetto\n"
                        "Contents of /home/u/.claude/memory/MEMORY.md (user's auto-memory):\n"
                        "memoria\n"
                        "</system-reminder>"
                    ),
                },
                {"type": "text", "text": "Provo ad allegare @docs/style.md e cito docs/other.md"},
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
                {"type": "text", "text": "Ecco un'immagine [Image #1]"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "Zm9v"}},
                {"type": "text", "text": "[Image: source: /home/u/.cache/1.png]"},
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
    assert set(kinds) == {"system", "claude-md", "memory", "image", "at-file", "tools"}


def test_system_excludes_billing_header():
    system = _by_kind(extract_artifacts(SAMPLE_BODY))["system"][0]
    # 1000 char di system prompt + "You are Claude Code." (20), NON il billing header
    assert system["chars"] == 1000 + len("You are Claude Code.")


def test_instruction_files_labelled():
    kinds = _by_kind(extract_artifacts(SAMPLE_BODY))
    labels = {a["label"] for a in kinds["claude-md"]}
    assert labels == {"CLAUDE.md (globale)", "CLAUDE.md (progetto)"}
    assert kinds["memory"][0]["path"].endswith("MEMORY.md")


def test_at_file_from_system_block_not_the_cited_one():
    at = _by_kind(extract_artifacts(SAMPLE_BODY))["at-file"]
    assert len(at) == 1
    assert at[0]["path"] == "docs/style.md"       # allegato via @
    assert at[0]["chars"] > 0                      # contenuto iniettato
    # il file "solo citato" (docs/other.md) non deve comparire
    assert all(a["path"] != "docs/other.md" for a in at)


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
    # system:null (chiamate token-count) → nessun artifact system, nessun errore
    assert extract_artifacts({"system": None, "messages": []}) == []
    # system come stringa
    out = extract_artifacts({"system": "prompt intero"})
    assert out and out[0]["kind"] == "system"


def test_system_fallback_when_no_billing_block():
    # se non c'è il billing header, non azzerare mai il system prompt
    body = {"system": [{"type": "text", "text": "You are a security monitor."}]}
    out = extract_artifacts(body)
    assert out[0]["kind"] == "system"
    assert out[0]["chars"] == len("You are a security monitor.")
