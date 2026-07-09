import pytest
import asyncio
from browser_optimizer.server.main import mcp

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_exposed_tools_list():
    """Verify that only meta-tools (list_tools, get_tool_schema) are exposed by default in list_tools()."""
    exposed = await mcp.list_tools()
    exposed_names = {t.name for t in exposed}
    
    # Check that ONLY the two meta-tools are exposed
    assert "list_tools" in exposed_names
    assert "get_tool_schema" in exposed_names
    
    # Check that other tools (e.g. extract_context, execute_action) are NOT in the initial exposed list
    assert "extract_context" not in exposed_names
    assert "execute_action" not in exposed_names


@pytest.mark.anyio
async def test_list_tools_meta_tool():
    """Verify that calling the list_tools meta-tool returns all actual optimization tools."""
    # Call list_tools meta-tool
    res, extra = await mcp.call_tool("list_tools", {})
    assert "result" in extra
    tools = extra["result"]["tools"]
    
    tool_names = {t["name"] for t in tools}
    
    # The returned list should contain our actual browser optimization tools
    assert "extract_context" in tool_names
    assert "execute_action" in tool_names
    assert "replay_skill" in tool_names
    
    # Meta-tools themselves should not be listed as optimization tools
    assert "list_tools" not in tool_names
    assert "get_tool_schema" not in tool_names


@pytest.mark.anyio
async def test_get_tool_schema_tool():
    """Verify that get_tool_schema returns the correct parameters schema for a tool."""
    res, extra = await mcp.call_tool("get_tool_schema", {"tool_name": "extract_context"})
    assert "result" in extra
    result = extra["result"]
    
    assert result["success"] is True
    assert result["tool_name"] == "extract_context"
    
    input_schema = result["input_schema"]
    assert "properties" in input_schema
    assert "url" in input_schema["properties"]
    assert "session_id" in input_schema["properties"]


@pytest.mark.anyio
async def test_unexposed_tool_execution():
    """Verify that a tool not exposed in list_tools() can still be successfully executed by name."""
    # Mock manager get_page so calling extract_context doesn't fail
    from browser_optimizer.browser.manager import manager
    
    class DummyPage:
        url = "https://example.com"
        async def title(self):
            return "Test Title"
        async def wait_for_load_state(self, state, timeout=None):
            pass
        async def content(self):
            return "<html></html>"
            
    async def mock_get_page(session_id="default"):
        return DummyPage()
        
    original_get_page = manager.get_page
    manager.get_page = mock_get_page
    
    try:
        # Call extract_context directly via call_tool
        res, extra = await mcp.call_tool("extract_context", {"url": "https://example.com", "session_id": "test_exec"})
        assert "result" in extra
        assert extra["result"]["url"] == "https://example.com"
        assert extra["result"]["title"] == "Test Title"
    finally:
        manager.get_page = original_get_page
