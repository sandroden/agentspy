#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.request

def main():
    try:
        # Read ALL of stdin
        input_data = sys.stdin.read()

        # Try to parse it as JSON
        try:
            payload = json.loads(input_data)
        except (json.JSONDecodeError, ValueError):
            # If it is not valid JSON, build {"raw": <truncated text>}
            payload = {"raw": input_data[:10000]}

        # Build the request body
        body = {
            "ts": time.time(),
            "tag": os.environ.get("AGENTSPY_TAG"),
            "payload": payload
        }

        # Work out the URL
        url = os.environ.get("AGENTSPY_URL", "http://127.0.0.1:8082") + "/ingest/hook"

        # Prepare the request
        body_json = json.dumps(body)
        req = urllib.request.Request(
            url,
            data=body_json.encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        # POST with a 0.5s timeout: the hook is synchronous in the Claude Code
        # loop (PreToolUse fires on every tool), a slow collector must not
        # stall the agent
        with urllib.request.urlopen(req, timeout=0.5) as response:
            pass

    except Exception:
        # Swallow ANY exception silently
        # Log to stderr only when AGENTSPY_DEBUG=1
        if os.environ.get("AGENTSPY_DEBUG") == "1":
            try:
                import traceback
                print(traceback.format_exc(), file=sys.stderr)
            except:
                pass

    # ALWAYS exit with code 0
    sys.exit(0)

if __name__ == "__main__":
    main()
