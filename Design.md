# Browser Optimizer MCP — v2 upgrade plan

A practical, buildable upgrade plan for `browser-optimizer-mcp`, scoped for a hackathon timeline. Each item includes what changes, why it matters, and how to implement it.

---

## Overview

v1 is a deterministic token/latency optimization layer: rule-based classification, exact-match caching, single-session execution, pull-based diffing. v2 keeps the same core function — it does not pivot into a multi-agent swarm or claim full autonomy — but adds memory, confidence-weighted decisions, and protocol-level efficiency so the tool gets faster and cheaper the more it's used.

Four upgrade layers, plus one protocol-level addition:

1. Perception layer
2. Memory layer
3. Execution layer
4. Observability layer
5. MCP protocol layer (new)

---

## 1. Perception layer

### 1.1 ML-based page classifier
**What:** Replace the current rule-based classifier (hardcoded if/else across 6 categories like LOGIN, SEARCH, CHECKOUT) with a trained lightweight model that generalizes to unseen page types and returns a confidence score.

**Why:** Rule-based classification breaks on any page structure you didn't explicitly code for. A trained classifier generalizes and tells the agent how sure it is.

**How to build:**
- Collect labeled examples: for each existing category, gather ~50-100 extracted ARIA/element feature sets (you already produce these via `extract_context`).
- Engineer features: element counts by type (inputs, buttons, links), presence of password fields, form structure, text patterns (e.g. "add to cart", "sign in").
- Train a small classifier — logistic regression or a shallow decision tree is enough at this scale; don't reach for a neural net unless you have time to spare.
- Output both the predicted category and a confidence score (0-1).
- Fall back to the old heuristic rules when confidence is below a threshold (e.g. 0.6), so you never regress below v1 behavior.

### 1.2 Visual fallback for unreadable pages
**What:** When DOM/ARIA extraction fails or returns near-empty results (canvas-heavy pages, heavily obfuscated SPAs), fall back to a screenshot + vision-model description instead of erroring out.

**Why:** Pure DOM parsing has a hard failure mode. A lightweight visual fallback means the tool degrades gracefully instead of dead-ending the agent's task.

**How to build:**
- Detect fallback trigger: interactive element count from `extract_context` below a threshold (e.g. <3 elements found).
- Take a screenshot via Playwright (`page.screenshot()`), compress it (resize, JPEG quality ~70%).
- Send to a vision-capable model (Claude or any multimodal API) with a prompt like "list the interactive elements visible in this screenshot with approximate positions."
- Return a simplified structured response mimicking the shape of `extract_context`'s normal output, so downstream tools don't need special-casing.
- Keep this path lightweight — no need for a self-hosted object-detection pipeline (e.g. OmniParser-style YOLOv8 + Florence-2); a single vision API call is enough for hackathon scope.

---

## 2. Memory layer

### 2.1 Persistent cache storage
**What:** Replace the in-memory `TTLCache` with a persistent store (SQLite is enough) so the cache survives process restarts.

**Why:** Currently every restart throws away all cached page states. Persistence means accumulated efficiency isn't lost between sessions.

**How to build:**
- Add a SQLite table: `cache(key TEXT PRIMARY KEY, value BLOB, created_at, ttl, hit_count)`.
- Swap the `TTLCache.get/set` calls for SQLite read/write, keeping the same interface so the rest of the codebase doesn't need to change.
- Add a periodic cleanup job (on startup or via a cron-style check) to purge expired entries.

### 2.2 Semantic similarity matching
**What:** Instead of only recognizing exact-match pages (via xxhash), recognize near-duplicate pages — same template, different data (e.g. different product ID, different user name).

**Why:** Two pages that are functionally identical but textually different currently miss the cache entirely, wasting the optimization.

**How to build:**
- Generate a lightweight embedding of the page's structural features (element types, layout, class names) — not the full text content, since that's what varies between "duplicates."
- Store embeddings alongside cache entries.
- On a new page, compute its embedding and do a nearest-neighbor search (cosine similarity) against stored entries.
- If similarity exceeds a threshold (e.g. 0.9), treat it as a cache hit and adapt the cached action sequence to the new page's specific element references.
- A simple vector similarity library (or even brute-force cosine similarity for small cache sizes) is sufficient — no need for a dedicated vector database at this scale.

### 2.3 Skill-level caching (not just page-level)
**What:** Cache action *sequences* ("how to log in on this type of site"), not just individual page states.

**Why:** This is where the real speed win is — an agent that's solved "log into a dashboard" once shouldn't have to re-derive the same sequence of clicks every time it sees a similar login page.

**How to build:**
- When a macro (see 3.2) completes successfully, store it keyed by the semantic embedding of the *starting page type*, not the specific URL.
- On a new task, check if a matching skill exists before starting fresh reasoning — if found, attempt replay (see 3.1 for confidence-gated reuse).

### 2.4 Confidence scores and trust decay
**What:** Attach a confidence score to every cached action/macro based on recent success rate. On failure, decay the score instead of a hard cache invalidation.

**Why:** v1's binary "cache hit or full reprocess" wastes information — a macro that worked 9 times and failed once shouldn't be thrown away entirely.

**How to build:**
- Add a `confidence` field to cache/skill entries, initialized at a base value (e.g. 0.8) on first success.
- On successful replay: `confidence = min(1.0, confidence + 0.05)`.
- On failed replay: `confidence = max(0.0, confidence - 0.3)` (decay faster than growth, so trust is easy to lose and slow to rebuild).
- Use this score to drive routing decisions in the execution layer (below).

---

## 3. Execution layer

### 3.1 Confidence-based routing
**What:** When a cached action or macro is retrieved, use its confidence score to decide: reuse directly, adapt with a fallback check, or discard and re-plan from scratch.

**Why:** Replaces the current binary logic (cache hit → reuse, cache miss → full reprocess) with a graduated response that matches how reliable the cached knowledge actually is.

**How to build:**
- Simple threshold routing is enough — no need for a trained model:
  - confidence ≥ 0.7 → reuse directly
  - 0.3 ≤ confidence < 0.7 → attempt reuse, but verify the result before proceeding (e.g. check expected post-action state)
  - confidence < 0.3 → skip reuse, let the agent reason fresh
- Log the outcome of each routing decision to keep confidence scores accurate over time.

### 3.2 Multi-session / multi-tab support
**What:** Support concurrent, isolated browser sessions instead of a single session.

**Why:** Real agent workflows often need to compare or act across multiple tabs/sites in the same task (e.g. comparing prices across 3 sites).

**How to build:**
- Extend the session manager to hold a dict of `{session_id: BrowserContext}` instead of a single global context.
- Add a `session_id` parameter to all MCP tools (`extract_context`, `execute_action`, etc.), defaulting to a "default" session for backward compatibility.
- Use Playwright's `browser.new_context()` per session for isolation (separate cookies/storage).

### 3.3 Action recording → replayable macros
**What:** Record a sequence of actions into a named, reusable macro instead of the agent re-deriving each step every time.

**Why:** This is the biggest demo-visible upgrade — turns the tool from a "read optimizer" into something closer to an automation layer.

**How to build:**
- Add a `record_macro(name)` mode: while active, every call to `execute_action` gets appended to an in-progress macro list along with the page state before/after.
- On `stop_recording()`, save the macro (name, ordered actions, starting page-type embedding) to the skill cache (2.3).
- Add `replay_macro(name, session_id)`: steps through the saved actions, using confidence-based routing (3.1) to decide whether to blindly replay or verify each step.
- On a replay step failure: don't abort the whole macro — fall back to letting the agent reason about just that one step, then resume the macro from the next step. This is the "deterministic replay with fallback" behavior discussed earlier.

---

## 4. Observability layer

### 4.1 Streaming / push-based diff
**What:** Add a push mode to `page_diff` so changes are reported automatically instead of only on request.

**Why:** Enables live-monitoring use cases (price trackers, dashboard watchers) that the current pull-based model can't support well.

**How to build:**
- Add a `watch_page(interval_seconds)` tool that polls the page on a timer and calls the existing diff logic.
- Push results over a WebSocket connection (or SSE) back to the connected client, rather than requiring an explicit `page_diff` call each time.
- Keep the existing pull-based `page_diff` unchanged for backward compatibility.

### 4.2 Metrics dashboard
**What:** A small live dashboard visualizing `get_metrics` output — tokens saved, cache hit rate, cost estimate over time.

**Why:** Currently `get_metrics` returns raw numbers with no visualization. This is cheap to build and has strong hackathon demo value.

**How to build:**
- Build a small local web page (plain HTML/JS or a lightweight framework) that polls `get_metrics` every few seconds.
- Show: running token-savings counter, cache hit rate over time (simple line chart), $ saved estimate (using a rough per-token cost assumption).
- Serve it from a small local HTTP server alongside the MCP server — no need for a hosted backend.

### 4.3 Lightweight session replay
**What:** A simple view showing the sequence of extracted page states and actions taken during a task — not a full DOM-snapshot recorder.

**Why:** Useful for debugging why a task didn't go as expected, and demo-friendly without the complexity of full session recording.

**How to build:**
- Log each `(timestamp, page_classification, action_taken, confidence_used, outcome)` tuple to a simple append-only log (SQLite table or JSON lines file) per task.
- Add a `get_session_replay(session_id)` tool that returns this log.
- Display it as a simple timeline list in the dashboard (4.2) — no need for full visual DOM playback.

---

## 5. MCP protocol layer (new)

### 5.1 Progressive tool disclosure
**What:** Instead of exposing all 8 tool schemas upfront to the connecting agent, expose one lightweight `list_tools` meta-tool. Full schemas are only returned when the agent picks a specific tool.

**Why:** This directly extends your existing token-reduction pitch — it's a protocol-level efficiency gain, not new ML infrastructure, and it's cheap to implement.

**How to build:**
- Add a meta-tool that returns just tool names + one-line descriptions (no full parameter schemas).
- Add a `get_tool_schema(tool_name)` tool that returns the full schema for one tool on demand.
- Update your MCP server's tool registration so the default exposed surface is minimal, and full schemas are lazily fetched.
- This is a config/registration change to your existing MCP server — it doesn't require modifying the underlying tool logic at all.

---

## Suggested build priority (for limited time before a deadline)

**Cheapest, highest demo value — build first:**
- 2.1 Persistent cache (SQLite)
- 4.2 Metrics dashboard
- 5.1 Progressive tool disclosure

**Core v2 differentiator — build if time allows:**
- 2.3 Skill-level caching
- 2.4 Confidence scores + trust decay
- 3.1 Confidence-based routing
- 3.3 Action recording / macros

**Nice-to-have, more effort:**
- 1.1 ML classifier
- 1.2 Visual fallback
- 3.2 Multi-session support
- 4.1 Streaming diff
- 4.3 Session replay

## What's intentionally out of scope

- Multi-user shared "swarm" memory across agents (needs multi-tenant auth + moderation)
- Self-repairing skills with versioned/branching lineage
- Reinforcement learning training loops (GRPO, live-web RL)
- GNN-based DOM/security analysis
- Full OmniParser-style vision stack (YOLOv8 + Florence-2, self-hosted)
- Stealth/anti-bot infrastructure (proxies, CAPTCHA solving)

These are legitimate research directions but each is a standalone project on its own — not buildable or honestly demoable within a hackathon timeline.