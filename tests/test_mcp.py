from __future__ import annotations

import asyncio
import os
from pathlib import Path

import yaml

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from mcp_app import mcp  # noqa: E402


def test_mcp_discovery_matches_every_openapi_operation():
    spec = yaml.safe_load((Path(__file__).parents[1] / "openapi.yaml").read_text(encoding="utf-8"))
    openapi_names = {
        operation["operationId"]
        for path in spec["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == openapi_names
    assert len(tools) == len(openapi_names) == 9


def test_mcp_input_schemas_preserve_required_arguments_and_bounds():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert tools["getDiaryEntry"].input_schema["required"] == ["entry_id"]
    assert tools["createDiaryEntry"].input_schema["required"] == ["content"]
    assert tools["replyToDiaryEntry"].input_schema["required"] == ["entry_id", "content"]
    assert tools["addDiaryMark"].input_schema["required"] == ["entry_id", "mark_type"]
    assert tools["deleteDiaryEntry"].input_schema["required"] == ["entry_id"]
    assert tools["createDiaryEntry"].input_schema["properties"]["content"]["minLength"] == 1
    assert tools["createDiaryEntry"].input_schema["properties"]["content"]["maxLength"] == 100000
    assert tools["getRecentDiaryEntries"].input_schema["properties"]["page_size"]["default"] == 10
