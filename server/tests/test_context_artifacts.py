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
        # L'LLM decide una Read (tool_use) e un Bash: solo la prima porta nel
        # contesto il contenuto di un file → un artifact `read-file`.
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


def test_read_file_from_llm_tool_use():
    read = _by_kind(extract_artifacts(SAMPLE_BODY))["read-file"]
    assert len(read) == 1                          # solo la Read, non il Bash
    assert read[0]["path"] == "src/main.py"        # path risalito via tool_use_id
    assert read[0]["label"] == "main.py"
    assert read[0]["chars"] == len("1\tprint('hi')\n")


def test_read_file_content_as_block_list():
    # `tool_result.content` può essere lista di blocchi, non solo stringa.
    body = {
        "messages": [
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/a/b.txt"}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1",
                 "content": [{"type": "text", "text": "riga uno"}, {"type": "text", "text": "riga due"}]},
            ]},
        ]
    }
    read = _by_kind(extract_artifacts(body))["read-file"]
    assert read[0]["chars"] == len("riga uno") + len("riga due")


# Body campione che riproduce la lettura di un PDF via `@`: Claude Code non fa
# eager loading (troppo grande), il modello chiama Read a blocchi di pagine e il
# tool_result arriva con uno stub testuale + le pagine come blocchi image
# FRATELLI del tool_result (caso reale osservato, evento 2230/2232).
PDF_READ_BODY = {
    "messages": [
        {"role": "user", "content": [{"type": "text", "text": "nel file @man.pdf ..."}]},
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
    # `@file` troppo grande per l'eager loading: Claude Code inietta solo un
    # avviso role:system → artefatto `file-ref` (referenziato, non caricato).
    notice = (
        "PDF file: /docs/man.pdf (13 pages, 1.4MB). This PDF is too large to read "
        'all at once. You MUST use the Read tool with the pages parameter to read '
        'specific page ranges (e.g., pages: "1-5"). Maximum 20 pages per request.'
    )
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "nel file @man.pdf ..."}]},
            # nel caso reale l'avviso condivide il blocco system con altre
            # notifiche (deferred tools): pesa solo il primo paragrafo
            {"role": "system", "content": notice + "\n\nThe following deferred tools are now available..."},
        ]
    }
    kinds = _by_kind(extract_artifacts(body))
    assert "at-file" not in kinds                  # nessun contenuto pre-caricato
    ref = kinds["file-ref"][0]
    assert ref["path"] == "/docs/man.pdf"
    assert ref["label"] == "@man.pdf"
    assert "non caricato" in ref["description"]
    assert ref["chars"] == len(notice)             # solo l'avviso, non il resto del blocco


def test_tool_result_images_are_not_user_images():
    # Le pagine del PDF (image fratelli di un tool_result) NON sono allegati
    # dell'utente: nessun artefatto `image`, niente bolla YOU fantasma.
    kinds = _by_kind(extract_artifacts(PDF_READ_BODY))
    assert "image" not in kinds


def test_read_file_weighs_sibling_images_and_accumulates():
    read = _by_kind(extract_artifacts(PDF_READ_BODY))["read-file"]
    # Letture ripetute dello stesso path → un solo artefatto, pesi sommati.
    assert len(read) == 1
    assert read[0]["path"] == "/docs/man.pdf"
    expected = (
        len("PDF pages extracted: 6 page(s)") + 100 + 200
        + len("PDF pages extracted: 7 page(s)") + 300
    )
    assert read[0]["chars"] == expected


def test_read_file_counts_images_inside_tool_result_content():
    # Immagini DENTRO `tool_result.content` (es. screenshot): contate nel peso.
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
