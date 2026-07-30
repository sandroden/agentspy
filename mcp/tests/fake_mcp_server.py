#!/usr/bin/env python3
"""Fake MCP server for the wrapper tests: reads line-delimited JSON-RPC from
stdin and answers initialize / tools/list / tools/call (fake "echo" tool).
After initialize it also sends a spontaneous notification without an id."""
import json
import sys


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        rpc_id = req.get("id")

        if method == "initialize":
            send({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake-mcp-server", "version": "0.0.1"},
                },
            })
            send({
                "jsonrpc": "2.0",
                "method": "notifications/spontaneous_ping",
                "params": {"hello": "world"},
            })
        elif method == "tools/list":
            send({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Returns the received input",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                            },
                        }
                    ]
                },
            })
        elif method == "tools/call":
            params = req.get("params") or {}
            send({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"content": [{"type": "text", "text": json.dumps(params)}]},
            })
        elif rpc_id is not None:
            send({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"unknown method: {method}"},
            })
        # unknown incoming notifications: ignored


if __name__ == "__main__":
    main()
