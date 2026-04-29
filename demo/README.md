# FreshMart Live CQRS Dashboard (TUI)

A terminal companion to the React UI demo. Same backend (PostgreSQL → Materialize → agent),
different framing: the layout is the demo's thesis.

```
+-- (1) YOU TYPE -----+-- (2) AGENT REASONS -+-- (3) MATERIALIZE (live) ---+
|                     |                      |                             |
|  > _                |  tool calls,         |  SUBSCRIBE to               |
|  history below      |  reasoning,          |  - inventory pricing mv     |
|                     |  results             |  - orders_with_lines_mv     |
+---------------------+----------------------+-----------------------------+
+-- LOAD --------------------+-- TIMING (the loop) -----------------------+
|  rolling orders/min        |  the four deltas, lower-is-better          |
+----------------------------+--------------------------------------------+
```

**Read it left to right: write -> reason -> reflect.** The spatial separation is the CQRS
story. The right pane is what the agent reads; the agent's writes appear there in <2s and
the agent's *next* observation in the middle pane reads them back. That round trip is the
demo.

## Run

The TUI runs **on the host**, not in Docker -- it needs a real terminal. Connects to the
already-exposed ports of the running stack.

```sh
# Bring up the stack first (in the repo root)
make up-agent           # starts PG, Materialize, API, agent, web UI

# Then in a second shell:
make demo-tui                                # live mode, default
make demo-tui ARGS="--scenario stockout-reroute"   # Phase 5: pre-staged scenario
```

Direct invocation:

```sh
cd demo
uv run -m demo_tui
```

## Keys

Chat-app conventions:

- `enter` -- submit current prompt to the agent
- `shift+enter` -- insert a newline (kitty-protocol terminals: Ghostty, kitty, recent
  WezTerm/iTerm)
- `ctrl+j` -- insert a newline (universal fallback; works in any terminal)
- `ctrl+shift+c` -- copy agent + Materialize panes to clipboard via OSC 52 (full
  debug-paste bundle)
- `f1` -- focus the input pane (or `esc` from anywhere)
- `f2` -- focus the agent pane to scroll back through tool calls
- `f3` -- focus the Materialize pane to scroll back through rows
- once a pane is focused, use `arrows` / `pgup` / `pgdown` / `home` / `end` to scroll
- `ctrl+c` -- quit

Mouse capture is **disabled**, so click-and-drag selects text natively in the terminal
just like any other app. Highlight an order number, hit **Cmd+C** (macOS) or **Ctrl+C**
(elsewhere) -- the terminal handles the clipboard.

> Why not `Cmd+Enter` to submit and `Cmd+C` to copy? Mac terminals don't forward Cmd
> to apps unless the app and the terminal both speak the kitty keyboard protocol --
> and even then, Cmd+C is reserved by macOS for native clipboard copy. So we use the
> portable Slack/Discord/iMessage convention instead.

## Configuration

Defaults assume the standard `make up-agent` setup. Override via env vars if needed:

| var | default |
|---|---|
| `DEMO_AGENT_URL` | `http://localhost:8081` |
| `DEMO_API_URL`   | `http://localhost:8080` |
| `DEMO_MZ_DSN`    | `host=localhost port=6875 user=materialize password=materialize dbname=materialize` |

## Build phases

- [x] **Phase 1** -- skeleton: layout renders, multi-line input + history work.
- [ ] **Phase 2** -- live feeds: SSE from agent, SUBSCRIBE from Materialize, load pulse.
- [ ] **Phase 3** -- output panels render real events.
- [ ] **Phase 4** -- timing/correlation: the "agent saw its own write" climax.
- [ ] **Phase 5** -- scenarios + record/replay (stage safety net).
- [ ] **Phase 6** -- polish (status dots, stage flag).

## Layout choice

Three columns, left to right:

1. **YOU TYPE (write side)** -- multi-line `TextArea`, prompt history below.
2. **AGENT REASONS** -- streaming SSE from the LangGraph agent: tool calls, results,
   reasoning. The "saw my write" line lights up green when the agent's re-observation
   reads a row it just inserted.
3. **MATERIALIZE (live read side)** -- streaming SUBSCRIBE rows. Rows that match an
   open agent-write are starred for ~2s.

The bottom row anchors what's happening:

- **LOAD** -- live order pulse from the load generator, sparkline + per-zone bars.
- **TIMING** -- the four deltas that define the feedback loop, color-graded.
