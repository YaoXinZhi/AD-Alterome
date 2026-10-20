"""Read AD-Alterome evidence through the MCP protocol."""

import asyncio
import json
from datetime import timedelta

from django.conf import settings
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class McpRetrievalError(RuntimeError):
    """A retrieval failure safe to report without provider details."""


def unpack_tool_result(result):
    if result.isError:
        raise McpRetrievalError("AD-Alterome MCP tool failed")
    payload = getattr(result, "structuredContent", None)
    if payload is None:
        blocks = [block.text for block in result.content if block.type == "text"]
        if len(blocks) != 1:
            raise McpRetrievalError("AD-Alterome MCP returned an invalid result")
        try:
            payload = json.loads(blocks[0])
        except (TypeError, ValueError):
            raise McpRetrievalError("AD-Alterome MCP returned invalid JSON") from None
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise McpRetrievalError("AD-Alterome MCP retrieval failed")
    if not isinstance(payload.get("data"), dict):
        raise McpRetrievalError("AD-Alterome MCP returned invalid evidence data")
    return payload


async def call_mcp_tool(tool_name, arguments):
    """Keep the transport and session within one task, including on cancellation."""
    timeout = float(settings.ADALTEROME_MCP_TIMEOUT)

    async def execute():
        async with streamablehttp_client(
            settings.ADALTEROME_MCP_URL,
            timeout=timeout,
            sse_read_timeout=timeout,
        ) as (read, write, _):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=timeout)
            ) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                return unpack_tool_result(result)

    try:
        return await asyncio.wait_for(execute(), timeout=timeout)
    except asyncio.CancelledError:
        raise
    except Exception:
        # SDK exceptions can include request URLs or remote response bodies.
        # The page must not expose or log those through chained exceptions.
        raise McpRetrievalError("AD-Alterome MCP retrieval is unavailable") from None
