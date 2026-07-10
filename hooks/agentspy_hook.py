#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.request

def main():
    try:
        # Leggi TUTTO lo stdin
        input_data = sys.stdin.read()

        # Tenta di parsare come JSON
        try:
            payload = json.loads(input_data)
        except (json.JSONDecodeError, ValueError):
            # Se non è JSON valido, crea {"raw": <testo troncato>}
            payload = {"raw": input_data[:10000]}

        # Costruisci il body della richiesta
        body = {
            "ts": time.time(),
            "tag": os.environ.get("AGENTSPY_TAG"),
            "payload": payload
        }

        # Determina l'URL
        url = os.environ.get("AGENTSPY_URL", "http://127.0.0.1:8082") + "/ingest/hook"

        # Prepara la richiesta
        body_json = json.dumps(body)
        req = urllib.request.Request(
            url,
            data=body_json.encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        # Fai POST con timeout di 0.5 secondi: l'hook è sincrono nel ciclo di
        # Claude Code (PreToolUse scatta a ogni tool), un collector lento non
        # deve stallare l'agente
        with urllib.request.urlopen(req, timeout=0.5) as response:
            pass

    except Exception:
        # Ignora QUALSIASI eccezione in silenzio
        # Log su stderr solo se AGENTSPY_DEBUG=1
        if os.environ.get("AGENTSPY_DEBUG") == "1":
            try:
                import traceback
                print(traceback.format_exc(), file=sys.stderr)
            except:
                pass

    # Esce SEMPRE con exit code 0
    sys.exit(0)

if __name__ == "__main__":
    main()
