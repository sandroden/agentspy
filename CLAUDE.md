# Goal
This project builds a mostly educational tool to spy on the communication
between Claude Code and LLMs, showing how it is composed:
 * system prompt
 * tools
 * user context
 * user prompt
 * tool request
 * agents

The idea is to exploit the payload of the hooks to spy on the content that is
transmitted.

A fundamental point is having an educational and agile tool to understand the
advantage of one strategy over another.

A similar project we can take inspiration from is here:
/home/sandro/src/git/claude-code-hooks-multi-agent-observability

where the main problem, in fact, is that the rendering of the data is not to
my liking. It is also worth evaluating whether to reuse the data-collection
part and render it in a different way.

Among the things I want to be able to do is to follow the flow of a subagent
or follow all the round trips that follow a user prompt, to understand how the
context is used — showing, for example, the context filling up visually, the
total, and where it is used.

## Knowledge (.okf/)

OKF knowledge bundle in `.okf/` — index in `.okf/index.md`.

- **Before** exploring by grepping or reading the code directly, consult
  `.okf/index.md` and the relevant concepts (OKF skill, "consume" mode). For
  actual changes, verify against the code anyway: the concepts may be out of
  date.
- **After** significant changes, evaluate whether to update the bundle (OKF
  skill, "maintain" mode), together with the commit proposal.
