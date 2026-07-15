"""Test del runtime opencode: vocabolario, parser (tool_hint, last_user_message,
command_snippet) ed estrazione artefatti su un body sintetico verosimile."""

from agentspy_server.runtimes import get_runtime
from agentspy_server.runtimes.opencode import OpencodeRuntime

# Body sintetico stile opencode sulla wire Anthropic:
# - system come lista di blocchi: prompt base + due file di istruzioni iniettati
#   col prefisso "Instructions from:" (AGENTS.md e CLAUDE.md);
# - un'immagine incollata dall'utente (messaggio senza tool_result);
# - una `read` decisa dall'LLM (tool_use → tool_result) che carica un file;
# - un `bash` (tool_use → tool_result) che NON è un file letto.
SAMPLE_BODY = {
    "system": [
        {"type": "text", "text": "You are opencode."},
        {"type": "text", "text": "Instructions from: /home/u/proj/AGENTS.md\nregole di progetto"},
        {"type": "text", "text": "Instructions from: /home/u/.claude/CLAUDE.md\nregole globali"},
    ],
    "tools": [{"name": "read"}, {"name": "bash"}],
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "ciao, guarda l'immagine"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "Zm9vYmFy"}},
            ],
        },
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_r1", "name": "read", "input": {"filePath": "src/app.ts"}},
                {"type": "tool_use", "id": "toolu_b1", "name": "bash", "input": {"command": "ls"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_r1", "content": "export const x = 1\n"},
                {"type": "tool_result", "tool_use_id": "toolu_b1", "content": "app.ts\n"},
            ],
        },
    ],
}


def _by_kind(artifacts):
    out = {}
    for a in artifacts:
        out.setdefault(a["kind"], []).append(a)
    return out


def test_get_runtime_opencode():
    rt = get_runtime("opencode")
    assert isinstance(rt, OpencodeRuntime)
    assert rt.name == "opencode"


def test_vocabolario():
    rt = OpencodeRuntime()
    assert rt.hook_user_prompt == "chat.message"
    assert rt.hook_pre_tool_use == "tool.execute.before"
    assert rt.hook_post_tool_use == "tool.execute.after"
    assert rt.hook_stop == "session.idle"
    assert rt.session_id_header == ""


def test_helper_stringa_vuota_non_matcha_per_sbaglio():
    """Gli slot vuoti del vocabolario non devono matchare None/"".

    Con hook_subagent_* e system_reminder_prefix vuoti, gli helper di base.py
    devono restare falsi per hook_name None/"" e per qualsiasi testo."""
    rt = OpencodeRuntime()
    assert rt.is_session_end("session.idle") is True
    assert rt.is_session_end("") is False
    assert rt.is_session_end(None) is False
    assert rt.is_subagent_hook("") is False
    assert rt.is_subagent_hook(None) is False
    assert rt.is_tool_call_hook("tool.execute.before") is True
    assert rt.is_tool_call_hook("") is False
    # system_reminder_prefix vuoto: nulla è un reminder (niente "".startswith("")).
    assert rt.is_system_reminder("qualsiasi testo") is False


def test_tool_hint():
    rt = OpencodeRuntime()
    assert rt.tool_hint("read", {"filePath": "src/app.ts"}) == "src/app.ts"
    assert rt.tool_hint("write", {"filePath": "a/b.py", "content": "..."}) == "a/b.py"
    assert rt.tool_hint("bash", {"command": "ls -la /tmp"}) == "ls -la /tmp"
    assert rt.tool_hint("grep", {"pattern": "foo", "path": "src"}) == "foo"
    assert rt.tool_hint("webfetch", {"url": "https://x.dev"}) == "https://x.dev"
    assert rt.tool_hint("task", {"description": "cerca bug", "prompt": "..."}) == "cerca bug"
    # fallback generico per tool sconosciuto: primo valore stringa
    assert rt.tool_hint("mcp__srv__do", {"q": "hey"}) == "hey"
    assert rt.tool_hint("bash", "non-dict") == ""


def test_command_snippet_sempre_none():
    rt = OpencodeRuntime()
    assert rt.command_snippet("qualsiasi testo, opencode non lascia marcatori") is None


def test_last_user_message():
    rt = OpencodeRuntime()
    last = rt.last_user_message(SAMPLE_BODY["messages"])
    assert last is not None
    # l'ultimo messaggio user è quello coi tool_result
    assert any(b.get("type") == "tool_result" for b in last["content"])


def test_extract_artifacts_kinds():
    rt = OpencodeRuntime()
    kinds = _by_kind(rt.extract_artifacts(SAMPLE_BODY))
    assert set(kinds) == {"system", "claude-md", "image", "read-file", "tools"}


def test_instruction_files_scorporati_dal_system():
    rt = OpencodeRuntime()
    kinds = _by_kind(rt.extract_artifacts(SAMPLE_BODY))
    labels = {a["label"] for a in kinds["claude-md"]}
    assert labels == {"AGENTS.md", "CLAUDE.md"}
    # non additivo: il system prompt pesa solo il prompt base, non i file di
    # istruzioni (che hanno un chip proprio).
    system = kinds["system"][0]
    assert system["chars"] < len("Instructions from: /home/u/proj/AGENTS.md")
    assert all(a["chars"] > 0 for a in kinds["claude-md"])


def test_read_file_solo_per_read_non_bash():
    rt = OpencodeRuntime()
    read_files = _by_kind(rt.extract_artifacts(SAMPLE_BODY))["read-file"]
    assert len(read_files) == 1
    assert read_files[0]["path"] == "src/app.ts"


def test_extract_artifacts_robusto():
    rt = OpencodeRuntime()
    assert rt.extract_artifacts(None) == []
    assert rt.extract_artifacts({}) == []
    assert rt.extract_artifacts({"messages": "non-lista"}) == []


def test_blocco_non_istruzione_dopo_agents_non_gli_e_attribuito():
    """Se dopo un file di istruzioni seguono altri blocchi system (mcp/skills),
    il loro peso deve restare sul system, non finire nel char count del file."""
    rt = OpencodeRuntime()
    body = {
        "system": [
            {"type": "text", "text": "Instructions from: /p/AGENTS.md\nregole"},
            {"type": "text", "text": "<mcp_instructions>" + "M" * 500 + "</mcp_instructions>"},
        ],
    }
    kinds = _by_kind(rt.extract_artifacts(body))
    agents = kinds["claude-md"][0]
    assert agents["chars"] == len("Instructions from: /p/AGENTS.md\nregole")
    assert kinds["system"][0]["chars"] >= 500


def test_extract_system_come_stringa():
    """Il system può arrivare come stringa concatenata: lo split delle istruzioni
    deve funzionare anche in quel caso."""
    rt = OpencodeRuntime()
    body = {
        "system": "You are opencode.\nInstructions from: /p/AGENTS.md\ncontenuto",
    }
    kinds = _by_kind(rt.extract_artifacts(body))
    assert kinds["claude-md"][0]["label"] == "AGENTS.md"
    assert kinds["system"][0]["chars"] > 0


def test_istruzioni_in_mezzo_a_blocco_unico():
    """Forma reale osservata sulla wire (opencode 1.18, E2E del 2026-07-16): il
    system è UN blocco che concatena prompt base, più file di istruzioni (il cui
    contenuto può avere righe vuote) e la sezione skills in coda. Ogni file va
    scorporato fino all'incipit della sezione successiva, non fino a fine blocco
    né fino alla prima riga vuota."""
    rt = OpencodeRuntime()
    claude_md = "Instructions from: /home/u/.claude/CLAUDE.md\n# Repo\nregola\n\n# Python\naltra regola\n"
    agents_md = "Instructions from: /p/AGENTS.md\n# Regole\nuna sola frase.\n\n"
    skills = "Skills provide specialized instructions and workflows for specific tasks.\n<available_skills>" + "S" * 300
    body = {"system": [{"type": "text", "text": "You are OpenCode.\n<env>...</env>\n" + claude_md + agents_md + skills}]}
    kinds = _by_kind(rt.extract_artifacts(body))
    per_label = {a["label"]: a["chars"] for a in kinds["claude-md"]}
    assert per_label["CLAUDE.md"] == len(claude_md)
    assert per_label["AGENTS.md"] == len(agents_md)
    # base + skills restano sul system, senza doppio conteggio
    assert kinds["system"][0]["chars"] == len("You are OpenCode.\n<env>...</env>\n") + len(skills)
