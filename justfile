# agentspy — service commands (https://just.systems)
#
# Overridable variables: `just port=8082 db=./server/agentspy.db up`

port := env_var_or_default("AGENTSPY_PORT", "8082")
db := env_var_or_default("AGENTSPY_DB", "./agentspy.db")
pidfile := ".agentspy.pid"
logfile := "agentspy.log"

# list the commands
default:
    @just --list

# build the UI only (served by the collector on /ui)
build:
    cd frontend && npm run build

# build the frontend, then start the collector in the background (default port 8082, DB server/agentspy.db)
up: build
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f {{pidfile}} ] && kill -0 "$(cat {{pidfile}})" 2>/dev/null; then
        echo "collector already running (pid $(cat {{pidfile}}))"; exit 0
    fi
    cd server
    AGENTSPY_PORT={{port}} AGENTSPY_DB={{db}} nohup uv run agentspy > ../{{logfile}} 2>&1 &
    echo $! > ../{{pidfile}}
    sleep 1
    if curl -sf "http://127.0.0.1:{{port}}/api/sessions" > /dev/null; then
        echo "collector on http://127.0.0.1:{{port}} (UI: /ui/, pid $(cat ../{{pidfile}}))"
    else
        echo "startup failed, see {{logfile}}"; exit 1
    fi

# stop the collector
down:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f {{pidfile}} ] && kill -0 "$(cat {{pidfile}})" 2>/dev/null; then
        kill "$(cat {{pidfile}})" && rm -f {{pidfile}}
        echo "collector stopped"
    else
        rm -f {{pidfile}}
        # fallback: any process listening on the port
        if fuser -k {{port}}/tcp 2>/dev/null; then
            echo "collector stopped (via port {{port}})"
        else
            echo "no collector running"
        fi
    fi

# restart the collector (down + up; migrations and rehydration run on start)
restart: down up

# is the collector running?
status:
    #!/usr/bin/env bash
    if [ -f {{pidfile}} ] && kill -0 "$(cat {{pidfile}})" 2>/dev/null; then
        echo "running (pid $(cat {{pidfile}}), port {{port}})"
    else
        echo "not running (or started outside just)"
    fi

# populate the demo DB and print how to run it
seed:
    cd server && AGENTSPY_DB={{db}} uv run python ../scripts/seed_demo.py
    @echo "now: just up   (or: cd server && AGENTSPY_DB={{db}} uv run agentspy)"

# run the collector tests
test:
    cd server && uv run pytest -q
