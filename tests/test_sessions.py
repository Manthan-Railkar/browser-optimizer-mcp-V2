import pytest
from typing import Dict, Any

from browser_optimizer.browser.manager import manager
from browser_optimizer.executor.executor import executor as action_executor
from browser_optimizer.server.main import (
    extract_context,
    execute_action,
    replay_skill,
    resume_skill,
    start_macro_recording,
    save_macro,
    close_session
)
from browser_optimizer.cache.db import macro_store


@pytest.fixture(autouse=True)
def clean_database_and_sessions(monkeypatch):
    """Clean all session state and database entries between tests, and mock Playwright for fast execution."""
    from browser_optimizer.cache.cache import semantic_cache
    semantic_cache.clear()

    # Clear active sessions in manager
    manager.sessions.clear()

    # Mock browser and context for browserless testing
    class DummyBrowser:
        async def new_context(self):
            class DummyContext:
                async def new_page(self):
                    class DummyPage:
                        url = "about:blank"
                        is_closed_flag = False
                        async def goto(self, url, timeout=None, wait_until=None):
                            self.url = url
                        async def content(self):
                            return "<html><body>Hello</body></html>"
                        async def title(self):
                            return "Dummy Page"
                        def is_closed(self):
                            return self.is_closed_flag
                        async def close(self):
                            self.is_closed_flag = True
                        async def wait_for_load_state(self, state, timeout=None):
                            pass
                        async def wait_for_selector(self, selector, timeout=None):
                            if selector == "#fail":
                                raise Exception("Selector not found")
                        async def click(self, selector):
                            pass
                        async def fill(self, selector, value):
                            pass
                        async def select_option(self, selector, value=None):
                            pass
                        async def evaluate(self, script):
                            pass
                        async def wait_for_timeout(self, timeout):
                            pass
                    return DummyPage()
                async def close(self):
                    pass
            return DummyContext()

    setattr(manager, "browser", DummyBrowser())

    # Clean macros table
    import sqlite3
    with sqlite3.connect("cache.db") as conn:
        conn.execute("DELETE FROM macros")
        conn.commit()

    yield
    # Clean up again at teardown
    manager.sessions.clear()


@pytest.mark.anyio
async def test_session_isolation():
    """Test that different session IDs run in completely isolated contexts."""
    page_default = await manager.get_page("default")
    page_custom = await manager.get_page("custom")

    # Assert they are distinct objects
    assert page_default is not page_custom

    # Navigate default session
    await manager.navigate("https://default.com", "default")
    assert page_default.url == "https://default.com"
    assert page_custom.url == "about:blank"

    # Close custom session
    await manager.close_session("custom")
    assert "custom" not in manager.sessions
    assert "default" in manager.sessions
    assert page_default.is_closed() is False


@pytest.mark.anyio
async def test_session_isolated_recording():
    """Test that recording actions in one session does not contaminate or bleed into another session."""
    # Start recording on session A
    await start_macro_recording("sessionA")
    assert action_executor.is_recording("sessionA") is True
    assert action_executor.is_recording("sessionB") is False

    # Execute action on session A (should be recorded in session A)
    await execute_action("click", "#btnA", None, "sessionA")

    # Execute action on session B (should not be recorded anywhere)
    await execute_action("click", "#btnB", None, "sessionB")

    # Save macro on session A
    res = await save_macro("MacroA", "PAGE", {}, "sessionA")
    assert res["success"] is True
    
    # Verify saved macro contains only session A's step
    macro = macro_store.get_macro(res["macro_id"])
    assert macro is not None
    assert len(macro["sequence"]) == 1
    assert macro["sequence"][0]["selector"] == "#btnA"


@pytest.mark.anyio
async def test_session_isolated_suspension_states():
    """Test that separate sessions can maintain independent macro suspension states concurrently."""
    # Create macro with failing second step
    sequence = [
        {"action": "click", "selector": "#ok", "value": None},
        {"action": "click", "selector": "#fail", "value": None}
    ]
    macro_id = macro_store.save_macro("Failing Macro", "TEST", sequence)

    # Replay on session A -> fails on second step -> suspends
    res_a = await replay_skill(macro_id, {}, session_id="sessionA")
    assert res_a["success"] is False
    assert res_a["failed_step_index"] == 1

    # Replay on session B -> fails on second step -> suspends
    res_b = await replay_skill(macro_id, {}, session_id="sessionB")
    assert res_b["success"] is False
    assert res_b["failed_step_index"] == 1

    from browser_optimizer.server.main import suspended_replays
    assert "sessionA" in suspended_replays
    assert "sessionB" in suspended_replays

    # Resume session A
    resume_a = await resume_skill({}, "sessionA")
    assert resume_a["success"] is True
    assert "sessionA" not in suspended_replays
    assert "sessionB" in suspended_replays

    # Resume session B
    resume_b = await resume_skill({}, "sessionB")
    assert resume_b["success"] is True
    assert "sessionB" not in suspended_replays


@pytest.mark.anyio
async def test_session_state_persistence(monkeypatch):
    """Test that session context storage state is saved to the SQLite store and restored on new context initialization."""
    from browser_optimizer.cache.db import session_state_store
    
    # Clear any existing state for test session
    session_state_store.clear_state("test-persist-session")
    
    dummy_state = {"cookies": [{"name": "session_id", "value": "xyz123", "domain": "example.com", "path": "/"}]}
    
    # We will mock the BrowserContext and Page to support storage_state() and tracking of calls to new_context()
    class MockContext:
        def __init__(self, storage_state=None):
            self.storage_state_arg = storage_state
            self.is_closed = False
        async def new_page(self):
            class DummyPage:
                url = "about:blank"
                async def goto(self, url, timeout=None, wait_until=None):
                    pass
                def is_closed(self):
                    return False
                async def close(self):
                    pass
            return DummyPage()
        async def storage_state(self):
            return dummy_state
        async def close(self):
            self.is_closed = True

    created_contexts = []

    class MockBrowser:
        async def new_context(self, storage_state=None):
            ctx = MockContext(storage_state=storage_state)
            created_contexts.append(ctx)
            return ctx
        async def close(self):
            pass

    # Use the mock browser in manager
    monkeypatch.setattr(manager, "browser", MockBrowser())
    
    # 1. First get page (should have no storage state)
    page1 = await manager.get_page("test-persist-session")
    assert "test-persist-session" in manager.sessions
    context1 = manager.sessions["test-persist-session"][0]
    assert getattr(context1, "storage_state_arg", None) is None
    
    # 2. Trigger navigate (should save state to DB)
    await manager.navigate("https://example.com", "test-persist-session")
    
    # Verify state was saved to the store
    saved = session_state_store.get_state("test-persist-session")
    assert saved == dummy_state
    
    # 3. Close the session (should save state and remove from manager.sessions)
    await manager.close_session("test-persist-session")
    assert "test-persist-session" not in manager.sessions
    
    # 4. Open the session again (should restore the storage state)
    page2 = await manager.get_page("test-persist-session")
    assert "test-persist-session" in manager.sessions
    context2 = manager.sessions["test-persist-session"][0]
    assert getattr(context2, "storage_state_arg", None) == dummy_state
    
    # Clean up
    session_state_store.clear_state("test-persist-session")


