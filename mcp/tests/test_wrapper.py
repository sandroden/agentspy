"""Test end-to-end del wrapper MCP: relay stdio fedele + spia degli eventi JSON-RPC.

Topologia: pytest (parent) -> subprocess wrapper.py -> subprocess fake_mcp_server.py.
Un HTTP server locale di cattura riceve i POST /ingest/mcp del wrapper.
"""
import http.server
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HERE = Path(__file__).parent
WRAPPER = HERE.parent / "agentspy_mcp_wrapper.py"
FAKE_SERVER = HERE / "fake_mcp_server.py"


class CaptureHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {"_raw": body.decode("utf-8", "replace")}
        self.server.captured.append(payload)
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # silenzia il log di default sopra stderr durante i test


@pytest.fixture
def capture_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), CaptureHandler)
    server.captured = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.fixture
def wrapper_proc(capture_server):
    env = os.environ.copy()
    env["AGENTSPY_URL"] = f"http://127.0.0.1:{capture_server.server_port}"
    env.pop("AGENTSPY_TAG", None)
    cmd = [
        sys.executable, str(WRAPPER),
        "--name", "fake-server",
        "--",
        sys.executable, str(FAKE_SERVER),
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    yield proc
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def send_line(proc, msg):
    line = (json.dumps(msg) + "\n").encode("utf-8")
    proc.stdin.write(line)
    proc.stdin.flush()


class StdoutReader:
    """Legge righe da uno stream bufferizzato in un thread dedicato e le
    espone via coda con timeout. Necessario perché selectors su uno stream
    già bufferizzato da io.BufferedReader può non rilevare dati già letti
    nel buffer Python (readahead), causando falsi timeout."""

    def __init__(self, stream):
        self._q = queue.Queue()
        self._t = threading.Thread(target=self._run, args=(stream,), daemon=True)
        self._t.start()

    def _run(self, stream):
        while True:
            line = stream.readline()
            self._q.put(line)
            if line == b"":
                break

    def read_line(self, timeout=5):
        try:
            line = self._q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("timeout leggendo una riga da stdout")
        if line == b"":
            raise EOFError("EOF su stdout del wrapper")
        return line

    def expect_eof(self, timeout=5):
        try:
            line = self._q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("timeout attendendo EOF su stdout")
        return line == b""


def wait_for_events(server, n, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(server.captured) >= n:
            return
        time.sleep(0.05)
    raise TimeoutError(f"attesi {n} eventi, ricevuti {len(server.captured)}: {server.captured}")


def test_relay_fedele_e_spia(wrapper_proc, capture_server):
    proc = wrapper_proc
    reader = StdoutReader(proc.stdout)

    # --- initialize ---
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "pytest"}}}
    expected_init_resp = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mcp-server", "version": "0.0.1"},
        },
    }
    expected_init_line = (json.dumps(expected_init_resp) + "\n").encode("utf-8")
    expected_notif = {"jsonrpc": "2.0", "method": "notifications/ping_spontanea", "params": {"hello": "world"}}
    expected_notif_line = (json.dumps(expected_notif) + "\n").encode("utf-8")

    send_line(proc, init_req)
    got_init_line = reader.read_line()
    assert got_init_line == expected_init_line, "risposta initialize non fedele byte-per-byte"

    got_notif_line = reader.read_line()
    assert got_notif_line == expected_notif_line, "notifica spontanea non fedele byte-per-byte"

    # --- tools/list ---
    list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    expected_list_resp = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {
                    "name": "echo",
                    "description": "Restituisce l'input ricevuto",
                    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
                }
            ]
        },
    }
    expected_list_line = (json.dumps(expected_list_resp) + "\n").encode("utf-8")
    send_line(proc, list_req)
    got_list_line = reader.read_line()
    assert got_list_line == expected_list_line, "risposta tools/list non fedele byte-per-byte"

    # --- tools/call ---
    call_params = {"name": "echo", "arguments": {"text": "ciao mondo"}}
    call_req = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": call_params}
    expected_call_resp = {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {"content": [{"type": "text", "text": json.dumps(call_params)}]},
    }
    expected_call_line = (json.dumps(expected_call_resp) + "\n").encode("utf-8")
    send_line(proc, call_req)
    got_call_line = reader.read_line()
    assert got_call_line == expected_call_line, "risposta tools/call non fedele byte-per-byte"

    # --- chiusura pulita: EOF su stdin -> il figlio esce -> exit code propagato ---
    proc.stdin.close()
    returncode = proc.wait(timeout=5)
    assert returncode == 0, f"exit code atteso 0, ottenuto {returncode}"

    # nessun output spurio: dopo le righe attese, stdout deve essere finito (EOF)
    assert reader.expect_eof(timeout=5), "output spurio inatteso su stdout"

    # --- verifica eventi accoppiati/notifica ricevuti dal server di cattura ---
    wait_for_events(capture_server, 4)  # initialize, notification, tools/list, tools/call
    events = capture_server.captured

    by_method = {}
    notifications = []
    for ev in events:
        if ev.get("kind") == "notification":
            notifications.append(ev)
        else:
            by_method[ev["method"]] = ev

    assert "initialize" in by_method
    init_ev = by_method["initialize"]
    assert init_ev["kind"] == "call"
    assert init_ev["rpc_id"] == 1
    assert init_ev["params"] == {"clientInfo": {"name": "pytest"}}
    assert init_ev["result"] == expected_init_resp["result"]
    assert init_ev["direction"] == "client->server"
    assert init_ev["server_name"] == "fake-server"

    assert "tools/list" in by_method
    list_ev = by_method["tools/list"]
    assert list_ev["rpc_id"] == 2
    assert list_ev["result"] == expected_list_resp["result"]

    assert "tools/call" in by_method
    call_ev = by_method["tools/call"]
    assert call_ev["rpc_id"] == 3
    assert call_ev["params"] == call_params
    assert call_ev["result"] == expected_call_resp["result"]

    assert len(notifications) == 1
    notif_ev = notifications[0]
    assert notif_ev["method"] == "notifications/ping_spontanea"
    assert notif_ev["params"] == {"hello": "world"}
    assert notif_ev["direction"] == "server->client"


def test_stderr_passthrough_and_default_name(capture_server):
    """Il nome del server di default è il basename del comando, e stderr passa senza modifiche."""
    env = os.environ.copy()
    env["AGENTSPY_URL"] = f"http://127.0.0.1:{capture_server.server_port}"
    cmd = [sys.executable, str(WRAPPER), "--", sys.executable, "-c", "import sys; sys.stderr.write('errore di prova\\n'); sys.stderr.flush()"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    proc.stdin.close()
    returncode = proc.wait(timeout=5)
    stderr_output = proc.stderr.read()
    stdout_output = proc.stdout.read()
    assert returncode == 0
    assert b"errore di prova" in stderr_output
    assert stdout_output == b""
