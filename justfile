# agentspy — comandi di servizio (https://just.systems)
#
# Variabili sovrascrivibili: `just port=8082 db=./server/agentspy.db up`

port := env_var_or_default("AGENTSPY_PORT", "8082")
db := env_var_or_default("AGENTSPY_DB", "./agentspy.db")
pidfile := ".agentspy.pid"
logfile := "agentspy.log"

# elenco dei comandi
default:
    @just --list

# compila la UI (servita dal collector su /ui)
build:
    cd frontend && npm run build

# avvia il collector in background (default porta 8082, DB server/agentspy.db)
up: build
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f {{pidfile}} ] && kill -0 "$(cat {{pidfile}})" 2>/dev/null; then
        echo "collector già attivo (pid $(cat {{pidfile}}))"; exit 0
    fi
    cd server
    AGENTSPY_PORT={{port}} AGENTSPY_DB={{db}} nohup uv run agentspy > ../{{logfile}} 2>&1 &
    echo $! > ../{{pidfile}}
    sleep 1
    if curl -sf "http://127.0.0.1:{{port}}/api/sessions" > /dev/null; then
        echo "collector su http://127.0.0.1:{{port}} (UI: /ui/, pid $(cat ../{{pidfile}}))"
    else
        echo "avvio fallito, vedi {{logfile}}"; exit 1
    fi

# ferma il collector
down:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f {{pidfile}} ] && kill -0 "$(cat {{pidfile}})" 2>/dev/null; then
        kill "$(cat {{pidfile}})" && rm -f {{pidfile}}
        echo "collector fermato"
    else
        rm -f {{pidfile}}
        # fallback: qualunque processo in ascolto sulla porta
        if fuser -k {{port}}/tcp 2>/dev/null; then
            echo "collector fermato (via porta {{port}})"
        else
            echo "nessun collector attivo"
        fi
    fi

# riavvia il collector (down + up; all'avvio partono migrazioni e reidratazione)
restart: down up

# stato del collector
status:
    #!/usr/bin/env bash
    if [ -f {{pidfile}} ] && kill -0 "$(cat {{pidfile}})" 2>/dev/null; then
        echo "attivo (pid $(cat {{pidfile}}), porta {{port}})"
    else
        echo "non attivo (o avviato fuori da just)"
    fi

# popola il DB dimostrativo e stampa come avviarlo
seed:
    cd server && AGENTSPY_DB={{db}} uv run python ../scripts/seed_demo.py
    @echo "ora: just up   (oppure: cd server && AGENTSPY_DB={{db}} uv run agentspy)"

# test del collector
test:
    cd server && uv run pytest -q
