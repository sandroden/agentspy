from starlette.testclient import TestClient

from agentspy_server.app import create_app


def test_api_sessions_events_and_stats(tmp_path):
    db_path = str(tmp_path / "api.db")
    app = create_app(db_path=db_path, upstream="http://unused.invalid")

    with TestClient(app) as client:
        store = app.state.store
        store.upsert_session("s1", tag="t1", started_at=1.0, ended_at=2.0, live=True)
        event_id = store.insert_event(
            session_id="s1",
            kind="round_trip",
            turn_index=0,
            ts_start=1.0,
            ts_end=1.5,
            ttfb_s=0.1,
            model="claude-x",
            status=200,
            input_tokens=5,
            output_tokens=3,
            cache_read_tokens=0,
            cache_write_tokens=0,
            payload={
                "request": {"body": {}, "analysis": {"system_chars": 10}},
                "response": {"message": {"content": [{"type": "text", "text": "ok"}]}},
            },
        )

        r = client.get("/api/sessions")
        assert r.status_code == 200
        sessions = r.json()
        assert any(s["id"] == "s1" and s["tag"] == "t1" for s in sessions)

        r = client.get("/api/sessions/s1/events")
        assert r.status_code == 200
        events = r.json()
        assert len(events) == 1
        assert events[0]["id"] == event_id
        assert events[0]["snippet"] == "ok"
        assert "payload" not in events[0]

        r = client.get(f"/api/events/{event_id}")
        assert r.status_code == 200
        full = r.json()
        assert full["payload"]["response"]["message"]["content"][0]["text"] == "ok"

        r = client.get("/api/events/999999")
        assert r.status_code == 404

        r = client.get("/api/sessions/s1/stats")
        assert r.status_code == 200
        stats = r.json()
        assert len(stats) == 1
        assert stats[0]["system_chars"] == 10


def test_api_delete_session_single(tmp_path):
    db_path = str(tmp_path / "del_api.db")
    app = create_app(db_path=db_path, upstream="http://unused.invalid")

    with TestClient(app) as client:
        store = app.state.store
        store.upsert_session("p", started_at=0.0, live=True)
        store.upsert_session("c", parent_session_id="p", started_at=1.0, live=True)
        store.insert_event(session_id="p", kind="round_trip", ts_start=0.0)
        store.insert_event(session_id="c", kind="round_trip", ts_start=1.0)

        r = client.delete("/api/sessions/p")
        assert r.status_code == 200
        assert set(r.json()["deleted"]) == {"p", "c"}

        assert client.get("/api/sessions").json() == []
        # gli eventi delle sessioni cancellate non sono più recuperabili
        assert client.get("/api/sessions/p/events").json() == []
        assert client.get("/api/sessions/c/events").json() == []


def test_api_delete_sessions_bulk(tmp_path):
    db_path = str(tmp_path / "del_bulk.db")
    app = create_app(db_path=db_path, upstream="http://unused.invalid")

    with TestClient(app) as client:
        store = app.state.store
        store.upsert_session("a", started_at=0.0, live=True)
        store.upsert_session("b", started_at=0.0, live=True)
        store.upsert_session("keep", started_at=0.0, live=True)
        store.insert_event(session_id="a", kind="round_trip", ts_start=0.0)
        store.insert_event(session_id="b", kind="round_trip", ts_start=0.0)

        r = client.post("/api/sessions/delete", json={"ids": ["a", "b", "nope"]})
        assert r.status_code == 200
        assert sorted(r.json()["deleted"]) == ["a", "b"]

        ids = {s["id"] for s in client.get("/api/sessions").json()}
        assert ids == {"keep"}

        # body senza 'ids' -> 400
        assert client.post("/api/sessions/delete", json={}).status_code == 400


def test_ingest_hook_creates_session_and_event(tmp_path):
    db_path = str(tmp_path / "api2.db")
    app = create_app(db_path=db_path, upstream="http://unused.invalid")

    with TestClient(app) as client:
        r = client.post(
            "/ingest/hook",
            json={
                "tag": "night-1",
                "payload": {
                    "session_id": "real-1",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "fai una cosa",
                },
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == "real-1"

        sessions = client.get("/api/sessions").json()
        assert any(s["id"] == "real-1" and s["tag"] == "night-1" for s in sessions)

        events = client.get("/api/sessions/real-1/events").json()
        assert len(events) == 1
        assert events[0]["kind"] == "hook"
        assert events[0]["subkind"] == "UserPromptSubmit"


def test_ingest_mcp_creates_event(tmp_path):
    db_path = str(tmp_path / "api3.db")
    app = create_app(db_path=db_path, upstream="http://unused.invalid")

    with TestClient(app) as client:
        r = client.post(
            "/ingest/mcp",
            json={
                "session_id": "real-1",
                "server_name": "fs",
                "method": "tools/call",
                "id": 1,
                "params": {"name": "read_file"},
                "result": {"ok": True},
                "ts_request": 10.0,
                "ts_response": 10.2,
            },
        )
        assert r.status_code == 200

        events = client.get("/api/sessions/real-1/events").json()
        assert len(events) == 1
        assert events[0]["kind"] == "mcp"
        assert events[0]["subkind"] == "fs:tools/call"
