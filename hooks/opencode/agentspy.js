// opencode plugin for agentspy: translates the native events of the opencode
// plugin API into the neutral format of the ingest API (POST /ingest/hook) and
// sends them fire-and-forget to the agentspy server.
//
// Mirror of ``hooks/agentspy_hook.py`` (the Claude Code hook script): there it
// is Claude Code invoking a script for every hook, here it is opencode calling
// our handlers in-process. The native-event -> neutral ingest fields
// (session_id, hook_event_name, tool_name, tool_input, tool_use_id, prompt,
// cwd) translation lives HERE, as the runtime layer boundary requires: the
// server already receives the neutral vocabulary (see runtimes/base.py and
// ingest.py).
//
// As hook_event_name values we use the NATIVE opencode event names
// (chat.message, tool.execute.before/after, session.idle): the tool is
// educational, the data must reflect the reality of the observed runtime. They
// must match the vocabulary declared in OpencodeRuntime.
//
// Installation: see README.md in this directory.

const AGENTSPY_URL = process.env.AGENTSPY_URL || "http://127.0.0.1:8082";
const AGENTSPY_TAG = process.env.AGENTSPY_TAG || null;
const INGEST_URL = AGENTSPY_URL.replace(/\/$/, "") + "/ingest/hook";

// Fire-and-forget POST: short timeout and NEVER propagate errors to opencode (a
// throw from a handler would bubble up into the agent's flow). The response is
// not awaited: the collector must not slow down tool execution.
function post(payload) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 500);
    fetch(INGEST_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ts: Date.now() / 1000, tag: AGENTSPY_TAG, payload }),
      signal: controller.signal,
    })
      .catch(() => {})
      .finally(() => clearTimeout(timer));
  } catch {
    // ignore any synchronous error (e.g. fetch not available)
  }
}

// User text of a chat.message: joins the text parts of the message.
function promptText(parts) {
  if (!Array.isArray(parts)) return undefined;
  const texts = parts
    .filter((p) => p && p.type === "text" && typeof p.text === "string")
    .map((p) => p.text);
  return texts.length ? texts.join("\n") : undefined;
}

// Note: we do NOT send agent_id. The server correlator, on receiving an
// agent_id together with the session_id, would route the event to a
// "sub-<agent_id>" child session (Claude Code subagent semantics). Correlating
// opencode subagents (child sessions via parentID, without dedicated
// start/stop hooks) is later work: until it exists, every event stays on the
// main session.
export const AgentSpy = async ({ directory }) => {
  const cwd = typeof directory === "string" ? directory : undefined;
  return {
    // User message: advances the turn on the correlator side.
    "chat.message": async (input, output) => {
      post({
        session_id: input.sessionID,
        hook_event_name: "chat.message",
        prompt: promptText(output && output.parts),
        cwd,
      });
    },

    // Tool call, before execution. In tool.execute.before the arguments are in
    // output.args (input only carries tool/sessionID/callID). The callID IS the
    // toolu_... id of the Anthropic wire API (verified E2E on 2026-07-16): sent
    // as tool_use_id it enables the join with the session.
    "tool.execute.before": async (input, output) => {
      post({
        session_id: input.sessionID,
        hook_event_name: "tool.execute.before",
        tool_name: input.tool,
        tool_input: output && output.args,
        tool_use_id: input.callID,
        cwd,
      });
    },

    // Outcome of a tool call (presentation only). Here the arguments are in
    // input.args.
    "tool.execute.after": async (input, output) => {
      post({
        session_id: input.sessionID,
        hook_event_name: "tool.execute.after",
        tool_name: input.tool,
        tool_input: input.args,
        tool_use_id: input.callID,
        cwd,
      });
    },

    // Event bus: we forward ONLY session.idle (it closes the turn: maps onto
    // hook_stop). The other events (message.updated, message.part.updated) fire
    // on every stream chunk and would flood the ingest.
    event: async ({ event }) => {
      if (!event || typeof event !== "object") return;
      if (event.type === "session.idle") {
        const sid = (event.properties || {}).sessionID;
        if (sid) post({ session_id: sid, hook_event_name: "session.idle", cwd });
      }
    },
  };
};
