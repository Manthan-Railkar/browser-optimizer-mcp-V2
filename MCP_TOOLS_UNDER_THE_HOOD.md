# MCP Tools: Under the Hood

This document provides a detailed technical breakdown of every tool exposed by the **Browser Optimizer MCP** server, specifying their parameters, return shapes, and the underlying logic that executes when they are invoked by the LLM.

---

## 1. Core Perception & Optimization Tools

### 1.1 `extract_context`
* **Parameters:**
  * `url` (string, required): The target webpage address.
  * `session_id` (string, optional, default: `"default"`): Identifier for tab isolation.
* **Returns:**
  * `url` (string)
  * `title` (string)
  * `ui` (list of dictionaries representing compressed interactive components)
  * `ax_tree` (dictionary representing the ARIA accessibility tree snapshot)
  * `classification` (dictionary with the predicted page type and score mapping)
  * `from_cache` / `from_semantic_cache` (booleans)
  * `compression_ratio_pct` (float)

#### Under the Hood Workflow:
1. **On-Demand Initialization:** Resolves if the browser manager and WebSocket server are running. If not, boots them.
2. **Context Resolution:** Obtains the tab/page corresponding to the `session_id`. If the current page URL does not match the target URL, it triggers an async navigation.
3. **Cache Lookup (Multi-Tier):**
   * **Exact Hash Check:** Generates a 64-bit `xxhash` of the page's raw HTML. If a match is found in the semantic cache, it instantly returns the cached result in `<1ms`, bypassing DOM parsing.
   * **Confidence Verification:** If the matched entry has low confidence (`0.3 <= confidence < 0.7`), it validates the state by cross-referencing the page's live `<title>` attribute. If it fails, the cache is ignored and confidence decays. If confidence is `< 0.3`, the cache is bypassed entirely.
   * **Semantic Layout Check:** If the exact hash misses, it checks layout similarity. If the structural layout matches the cached template above `0.9` cosine similarity, it extracts fresh element values (such as labels or values) but skips re-calculating the classification, returning it as a `semantic_cache_hit`.
4. **Context Compression:** If a full cache miss occurs, the HTML is passed to the Compressor. This module strips out style sheets, analytical scripts, raw SVGs, and advertisements. It isolates interactable element selectors (`button`, `input`, `textarea`, `select`, `a`) and generates a clean ARIA snapshot tree.
5. **Heuristic/ML Classification:** The compressed element footprint is run through the local LightGBM model to predict the page category (e.g. `LOGIN`, `SEARCH`, `CHECKOUT`).
6. **Persistence & Metrics:** Stores the new page signature in the SQLite database cache, logs compression ratios, and records an event in the session replay log.

---

### 1.2 `page_diff`
* **Parameters:**
  * `url` (string, required)
  * `session_id` (string, optional, default: `"default"`)
* **Returns:**
  * `added` (list of new interactive elements)
  * `removed` (list of elements no longer present)
  * `changed` (list of elements whose parameters or tags altered)

#### Under the Hood Workflow:
1. **Target Extraction:** Calls the local `extract_context` function for the URL.
2. **State Retrieval:** Queries the difference engine for the previous state signature of this URL.
3. **Element Fingerprinting:** Generates unique hash keys for each element based on its selector path, tag name, type, and surrounding text.
4. **Delta Calculation:** Computes set differences to return lists of added, removed, and changed nodes, updating the state signature store with the current page state.

---

### 1.3 `execute_action`
* **Parameters:**
  * `action` (string, required): One of `"click"`, `"type"`, `"select"`, `"scroll"`, `"wait"`, `"navigate"`.
  * `selector` (string, optional): Target CSS selector.
  * `value` (string, optional): Input value for text writing or dropdown options.
  * `session_id` (string, optional, default: `"default"`)
* **Returns:**
  * `success` (boolean)
  * `message` (string)
  * `url` / `title` (strings)

#### Under the Hood Workflow:
1. **Target Page Acquisition:** Retrieves the page object for the specified `session_id`.
2. **Action Logging:** Resolves the current page type to tag the transaction event.
3. **Macro Recording Hook:** If macro recording is enabled for the session, the action, selector, and value are appended to the recording buffer.
4. **Playwright Execution:** Invokes the appropriate Playwright function:
   * `"click"`: Performs a mouse click at the element's coordinates after waiting for it to be visible.
   * `"type"`: Enters string content into text fields or textareas.
   * `"select"`: Chooses an option in standard dropdown menus.
   * `"scroll"`: Performs viewport scrolling.
5. **State Synchronization:** Triggers `manager.save_session_state(session_id)` to write current cookies, session tokens, and local storage states to the SQLite store.
6. **Trust & Reliability Adjustment:**
   * **On Success:** Increments the confidence score of the current page's cached macros by `+0.05` (capped at `1.0`).
   * **On Failure:** Decays the confidence score of the current page's cached macros by `-0.3` to mark it as untrustworthy.

---

## 2. Page Analysis & Utility Tools

### 2.1 `summarize_page`
* **Parameters:**
  * `url` (string, required)
  * `session_id` (string, optional)
* **Returns:**
  * `url` (string)
  * `title` (string)
  * `page_type` (string)
  * `summary` (string: concise textual narrative)
  * `element_counts` (dictionary of button, input, select, and link counts)

#### Under the Hood Workflow:
1. Calls `extract_context` to fetch the compressed element list and page metadata.
2. Loops through the elements list, tallying counts by tag type.
3. Obtains raw text snippets from the semantic cache (up to 300 characters).
4. Formulates a human-readable text block summarizing the layout structure and textual summary.

---

### 2.2 `classify_page`
* **Parameters:**
  * `url` (string, required)
  * `session_id` (string, optional)
* **Returns:**
  * `page_type` (string: `LOGIN`, `SEARCH`, `CHECKOUT`, etc.)
  * `scores` (dictionary of class probability scores)

#### Under the Hood Workflow:
1. Calls `extract_context` on the URL.
2. Directly returns the computed classification object generated by the ML Page Classifier.

---

### 2.3 `wait_until_ready`
* **Parameters:**
  * `url` (string, required)
  * `timeout` (integer, optional): Maximum wait time in milliseconds.
  * `session_id` (string, optional)
* **Returns:**
  * `success` (boolean)
  * `message` (string)
  * `url` (string)

#### Under the Hood Workflow:
1. Resolves the browser context and page instance.
2. Calls Playwright's `page.goto(url)` with the constraint `wait_until="networkidle"`.
3. Pauses until network activities cease (no requests for 500ms) or the timeout expires.
4. Saves cookies and updates session storage.

---

### 2.4 `cache_lookup`
* **Parameters:**
  * `url` (string, required)
  * `session_id` (string, optional)
* **Returns:**
  * `cached` (boolean)
  * `context` (dictionary of cached element arrays, if found)
  * `timestamp` (string)

#### Under the Hood Workflow:
1. Direct index lookup in the cache store without triggering a live network navigation. Useful for inspecting existing local cache states quickly.

---

## 3. Skill & Automation Macros Tools

### 3.1 `start_macro_recording` / `save_macro`
* **Parameters (`save_macro`):**
  * `name` (string, required): Descriptive name of the macro.
  * `page_type` (string, required): Target starting page type.
  * `parameters_map` (dictionary, required): Value mapping for variable extraction.
* **Returns:**
  * `success` (boolean)
  * `macro_id` (integer)

#### Under the Hood Workflow:
1. **Recording Initiation:** `start_macro_recording` flags the action executor to capture every sequential input command.
2. **Replay Parametrization:** During `save_macro`, the executor iterates through all logged steps. It replaces exact values matching the `parameters_map` values with placeholders (e.g. replacing a raw input text `"my_password"` with `"{password}"`).
3. **Database Storage:** Serializes the step list and saves it under the table `macros` inside the SQLite database, initialized with a confidence score of `0.8`.

---

### 3.2 `replay_skill` / `resume_skill`
* **Parameters (`replay_skill`):**
  * `macro_id` (integer, required)
  * `parameters` (dictionary, required): Dynamic credentials or values to inject.
  * `expected_url` / `expected_page_type` (strings, optional): Assertions for validation.
  * `session_id` (string, optional)
* **Returns:**
  * `success` (boolean)
  * `failed_step_index` (integer, if failed)
  * `message` (string)

#### Under the Hood Workflow:
1. **Sanity & Confidence Check:** Reads the macro from the database. If the macro confidence is `< 0.3`, it aborts, instructing the LLM to design steps from scratch.
2. **Parameter Substitution:** Intercepts each step and replaces any bracketed placeholders with the values provided in `parameters`.
3. **Step-by-Step Replay:** Executes each action sequentially. If a step fails:
   * Saves the execution state (macro ID, next step index, injected values) to `suspended_replays`.
   * Decays the macro's global confidence score.
   * Suspends execution and returns a detailed failure report, prompting the LLM to execute the single failed step manually via `execute_action`.
4. **Resuming:** The LLM calls `resume_skill` once it resolves the block, which reads the state from `suspended_replays` and attempts to complete the remaining steps.
5. **Post-State Validation:** If `expected_url` or `expected_page_type` is provided, it verifies the final page state. If a mismatch is detected, it decays the macro confidence score and returns a failure warning. If successful, confidence is incremented.

---

## 4. Push Observability & Diagnostics

### 4.1 `watch_page` / `stop_watch_page`
* **Parameters (`watch_page`):**
  * `url` (string, required)
  * `interval_seconds` (integer, optional, default: `5`)
  * `session_id` (string, optional)

#### Under the Hood Workflow:
1. **Poller Spawning:** `watch_page` cancels any existing polling loops for the session and spawns a background `asyncio.create_task` running `poll_page_diff`.
2. **WebSocket Broadcasting:** Every `interval_seconds`, the poller runs the `page_diff` tool. If structural differences are detected, the payload is serialized and broadcasted across active WebSockets registered for that `session_id`.
3. **Teardown:** `stop_watch_page` cancels the task and removes it from the memory lookup table.

---

### 4.2 `list_tools` / `get_tool_schema` (Progressive Tool Disclosure)
* **Under the Hood Workflow:**
  * During the initial Model Context Protocol handshake, the server overrides the standard `list_tools` behavior, returning *only* two meta-tools: `list_tools` and `get_tool_schema`.
  * The LLM queries `list_tools` to get a high-level summary of available functions.
  * When the LLM decides to invoke a specific tool, it calls `get_tool_schema(tool_name)` to lazily retrieve the parameters and type specifications for that tool only, eliminating massive schema payloads from the initial connection prompt.
