// Plugin opencode per agentspy: traduce gli eventi nativi del plugin API di
// opencode nel formato neutro dell'ingest API (POST /ingest/hook) e li spedisce
// fire-and-forget al server agentspy.
//
// Speculare a ``hooks/agentspy_hook.py`` (lo script hook di Claude Code): lì è
// Claude Code a invocare uno script per ogni hook, qui è opencode a chiamare i
// nostri handler in-process. La traduzione evento-nativo -> campi neutri
// dell'ingest (session_id, hook_event_name, tool_name, tool_input, tool_use_id,
// prompt, cwd) vive QUI, come vuole il confine del layer runtime: il server
// riceve già il vocabolario neutro (vedi runtimes/base.py e ingest.py).
//
// Come i nomi degli hook_event_name usiamo i nomi NATIVI degli eventi opencode
// (chat.message, tool.execute.before/after, session.idle): lo strumento è
// didattico, i dati devono riflettere la realtà del runtime osservato. Devono
// combaciare con il vocabolario dichiarato in OpencodeRuntime.
//
// Installazione: vedi README.md in questa cartella.

const AGENTSPY_URL = process.env.AGENTSPY_URL || "http://127.0.0.1:8082";
const AGENTSPY_TAG = process.env.AGENTSPY_TAG || null;
const INGEST_URL = AGENTSPY_URL.replace(/\/$/, "") + "/ingest/hook";

// POST fire-and-forget: timeout corto e MAI propagare errori a opencode (un
// throw da un handler risalirebbe nel flusso dell'agente). Non si attende la
// risposta: il collector non deve rallentare l'esecuzione dei tool.
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
    // ignora qualsiasi errore sincrono (es. fetch non disponibile)
  }
}

// Testo utente di un chat.message: concatena i part testuali del messaggio.
function promptText(parts) {
  if (!Array.isArray(parts)) return undefined;
  const texts = parts
    .filter((p) => p && p.type === "text" && typeof p.text === "string")
    .map((p) => p.text);
  return texts.length ? texts.join("\n") : undefined;
}

// Nota: NON inviamo agent_id. Il correlatore del server, ricevendo un agent_id
// insieme al session_id, instraderebbe l'evento verso una sessione figlia
// "sub-<agent_id>" (semantica dei subagenti Claude Code). La correlazione dei
// subagenti opencode (sessioni figlie via parentID, senza hook start/stop
// dedicati) è lavoro successivo: finche' non c'e', ogni evento resta sulla
// sessione principale.
export const AgentSpy = async ({ directory }) => {
  const cwd = typeof directory === "string" ? directory : undefined;
  return {
    // Messaggio dell'utente: avanza il turno lato correlatore.
    "chat.message": async (input, output) => {
      post({
        session_id: input.sessionID,
        hook_event_name: "chat.message",
        prompt: promptText(output && output.parts),
        cwd,
      });
    },

    // Chiamata a un tool, prima dell'esecuzione. In tool.execute.before gli
    // argomenti stanno in output.args (input porta solo tool/sessionID/callID).
    // Il callID E' l'id toolu_... della wire API Anthropic (verificato in E2E
    // il 2026-07-16): mandato come tool_use_id abilita il join con la sessione.
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

    // Esito di una chiamata tool (solo presentazione). Qui gli argomenti sono
    // in input.args.
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

    // Bus eventi: inoltriamo SOLO session.idle (chiude il turno: mappa su
    // hook_stop). Gli altri eventi (message.updated, message.part.updated)
    // scattano a ogni chunk dello stream e inonderebbero l'ingest.
    event: async ({ event }) => {
      if (!event || typeof event !== "object") return;
      if (event.type === "session.idle") {
        const sid = (event.properties || {}).sessionID;
        if (sid) post({ session_id: sid, hook_event_name: "session.idle", cwd });
      }
    },
  };
};
