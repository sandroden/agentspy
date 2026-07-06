#!/usr/bin/env python3
"""Wrapper stdio trasparente per server MCP.

Uso:
    agentspy_mcp_wrapper.py [--name NAME] [--url URL] -- comando args...

Lancia <comando args...> come sottoprocesso e relaya il suo stdio nei due
sensi (parent stdin -> child stdin, child stdout -> parent stdout) byte per
byte, riga per riga (il protocollo MCP stdio è JSON-RPC line-delimited).
Ogni riga viene anche "spiata": se è JSON valido viene classificata come
request/notification/response e le coppie request<->response (per "id")
vengono POSTate a {url}/ingest/mcp. Il relay ha priorità assoluta: se lo
spione fallisce o l'endpoint non risponde, la riga viene comunque inoltrata
senza modifiche e senza ritardi percepibili.
"""
import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import urllib.request

MAX_LEN = 200_000       # troncamento params/result serializzati
POST_TIMEOUT = 2.0      # timeout per singola POST
DRAIN_TIMEOUT = 2.0     # tempo massimo complessivo per svuotare la coda a fine processo


def debug(msg):
    if os.environ.get("AGENTSPY_DEBUG") == "1":
        print(f"[agentspy-mcp-wrapper] {msg}", file=sys.stderr, flush=True)


def parse_args(argv):
    if "--" not in argv:
        print(
            "uso: agentspy_mcp_wrapper.py [--name NAME] [--url URL] -- comando args...",
            file=sys.stderr,
        )
        sys.exit(2)
    idx = argv.index("--")
    own_args = argv[:idx]
    command = argv[idx + 1:]
    if not command:
        print("errore: nessun comando specificato dopo '--'", file=sys.stderr)
        sys.exit(2)

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--url", default=None)
    ns = parser.parse_args(own_args)

    name = ns.name or os.path.basename(command[0])
    url = ns.url or os.environ.get("AGENTSPY_URL", "http://127.0.0.1:8082")
    tag = os.environ.get("AGENTSPY_TAG")
    return name, url.rstrip("/"), tag, command


def classify(msg):
    """request (method+id) | notification (method senza id) | response (id senza method)."""
    has_method = "method" in msg
    has_id = "id" in msg
    if has_method and has_id:
        return "request"
    if has_method and not has_id:
        return "notification"
    if has_id and not has_method:
        return "response"
    return None


def maybe_truncate(value):
    """Ritorna (valore_per_json, truncated). Tronca solo se la serializzazione supera MAX_LEN."""
    if value is None:
        return None, False
    try:
        s = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(value)
        return (s[:MAX_LEN], True) if len(s) > MAX_LEN else (s, False)
    if len(s) > MAX_LEN:
        return s[:MAX_LEN], True
    return value, False


class Spy:
    """Accoppia request->response per rpc id e prepara gli eventi per la coda HTTP."""

    def __init__(self, server_name, tag, http_queue):
        self.server_name = server_name
        self.tag = tag
        self.http_queue = http_queue
        self.pending = {}
        self.lock = threading.Lock()

    def feed(self, raw_line, direction):
        try:
            self._feed(raw_line, direction)
        except Exception as e:  # la spia non deve MAI rompere il relay
            debug(f"errore spia (ignorato): {e!r}")

    def _feed(self, raw_line, direction):
        text = raw_line.decode("utf-8", errors="replace").strip()
        if not text:
            return
        try:
            msg = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return  # non JSON: già inoltrata dal relay, nulla da spiare
        if not isinstance(msg, dict):
            return

        kind = classify(msg)
        now = time.time()

        if kind == "request":
            rpc_id = msg.get("id")
            with self.lock:
                self.pending[rpc_id] = {
                    "method": msg.get("method"),
                    "params": msg.get("params"),
                    "ts": now,
                    "direction": direction,
                }
            return

        if kind == "response":
            rpc_id = msg.get("id")
            with self.lock:
                entry = self.pending.pop(rpc_id, None)
            if entry is None:
                debug(f"risposta senza richiesta corrispondente in pending (id={rpc_id!r})")
                return
            event = {
                "server_name": self.server_name,
                "tag": self.tag,
                "kind": "call",
                "method": entry["method"],
                "rpc_id": rpc_id,
                "ts_request": entry["ts"],
                "ts_response": now,
                "direction": entry["direction"],
            }
            truncated = False
            params_val, p_trunc = maybe_truncate(entry["params"])
            event["params"] = params_val
            truncated = truncated or p_trunc
            if "error" in msg:
                err_val, e_trunc = maybe_truncate(msg.get("error"))
                event["error"] = err_val
                truncated = truncated or e_trunc
            else:
                res_val, r_trunc = maybe_truncate(msg.get("result"))
                event["result"] = res_val
                truncated = truncated or r_trunc
            if truncated:
                event["truncated"] = True
            self._enqueue(event)
            return

        if kind == "notification":
            event = {
                "server_name": self.server_name,
                "tag": self.tag,
                "kind": "notification",
                "method": msg.get("method"),
                "ts": now,
                "direction": direction,
            }
            params_val, p_trunc = maybe_truncate(msg.get("params"))
            event["params"] = params_val
            if p_trunc:
                event["truncated"] = True
            self._enqueue(event)
            return

    def _enqueue(self, event):
        try:
            self.http_queue.put_nowait(event)
        except Exception as e:
            debug(f"impossibile accodare evento (ignorato): {e!r}")


def http_worker(http_queue, ingest_url, stop_event):
    while True:
        try:
            item = http_queue.get(timeout=0.5)
        except queue.Empty:
            if stop_event.is_set():
                return
            continue
        try:
            body = json.dumps(item).encode("utf-8")
            req = urllib.request.Request(
                ingest_url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=POST_TIMEOUT):
                pass
        except Exception as e:
            debug(f"POST a {ingest_url} fallita (scartata): {e!r}")
        finally:
            http_queue.task_done()


def pump_stdin_to_child(child_stdin, spy):
    """parent stdin -> child stdin, riga per riga, byte identici."""
    src = sys.stdin.buffer
    try:
        while True:
            line = src.readline()
            if line == b"":
                break
            try:
                child_stdin.write(line)
                child_stdin.flush()
            except (BrokenPipeError, OSError):
                break
            spy.feed(line, "client->server")
    finally:
        try:
            child_stdin.close()
        except Exception:
            pass


def pump_child_stdout_to_parent(child_stdout, spy):
    """child stdout -> parent stdout, riga per riga, byte identici."""
    dst = sys.stdout.buffer
    while True:
        line = child_stdout.readline()
        if line == b"":
            break
        try:
            dst.write(line)
            dst.flush()
        except Exception:
            break
        spy.feed(line, "server->client")


def pump_child_stderr_to_parent(child_stderr):
    """child stderr -> parent stderr, passthrough puro."""
    dst = sys.stderr.buffer
    while True:
        chunk = child_stderr.read(4096)
        if chunk == b"":
            break
        try:
            dst.write(chunk)
            dst.flush()
        except Exception:
            break


def main():
    name, url, tag, command = parse_args(sys.argv[1:])
    ingest_url = url + "/ingest/mcp"

    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    http_queue = queue.Queue()
    stop_event = threading.Event()
    spy = Spy(name, tag, http_queue)

    def handle_signal(signum, frame):
        debug(f"segnale {signum} ricevuto: termino il processo figlio")
        try:
            child.terminate()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    threads = [
        threading.Thread(target=pump_stdin_to_child, args=(child.stdin, spy), daemon=True),
        threading.Thread(target=pump_child_stdout_to_parent, args=(child.stdout, spy), daemon=True),
        threading.Thread(target=pump_child_stderr_to_parent, args=(child.stderr,), daemon=True),
        threading.Thread(target=http_worker, args=(http_queue, ingest_url, stop_event), daemon=True),
    ]
    for t in threads:
        t.start()

    returncode = child.wait()

    # il figlio è uscito: dai un attimo ai pump di stdout/stderr di svuotare
    # quel che resta nei pipe, poi segnala allo http_worker di fermarsi.
    threads[1].join(timeout=2)
    threads[2].join(timeout=2)
    stop_event.set()

    deadline = time.time() + DRAIN_TIMEOUT
    while not http_queue.empty() and time.time() < deadline:
        time.sleep(0.05)

    sys.exit(returncode if returncode is not None else 0)


if __name__ == "__main__":
    main()
