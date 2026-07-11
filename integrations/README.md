# ByrdHouse studio and MCP endpoints

These JSON files use the mcpServers shape accepted by LM Studio and Cherry
Studio for local STDIO servers. Use the GAMING file on GAMING and the MINI file
on MINI. Cherry Studio can enter the same values through Settings -> MCP
Servers -> Add Server -> STDIO.

## Endpoint ownership

| Capability | Endpoint | Owner |
|---|---|---|
| ByrdHouse belt and bot tools | http://byrd-mini:8787 | MINI |
| LM Studio OpenAI-compatible API | http://byrd-gaming:1234/v1 | GAMING |
| LM Studio model list | http://byrd-gaming:1234/v1/models | GAMING |
| ComfyUI | http://byrd-gaming:8188 | GAMING worker only |
| Belt MCP transport | local STDIO process | client machine |

The MCP process reads services.router and auth.admin_token from the
machine-local byrdhouse.config.json; the JSON template must never contain a
token. Keep BYRD_BELT_MCP_READONLY=1 until the read-only acceptance test
passes.

## LM Studio settings

On GAMING, set the server port to 1234, enable Serve on Local Network and
Enable CORS, and verify:

GET http://localhost:1234/v1/models
GET http://byrd-gaming:1234/v1/models

For LM Studio itself to call servers from mcp.json, enable its
Allow calling servers from mcp.json setting. Keep file-system and browser
servers out of this first belt test; expose only byrdhouse-belt.

LM Studio documents that API clients using this setting also require server
authentication. Do not enable Require Authentication on the GAMING API until
the optional LM API token is configured for the ByrdHouse worker; the current
worker intentionally assumes the existing unauthenticated private-LAN API.

## Cherry Studio settings

Use the same mcpServers entry from the appropriate JSON file as a STDIO
server. The model provider endpoint is separate: configure an
OpenAI-compatible provider with base URL http://byrd-gaming:1234/v1, then
enable the byrdhouse-belt MCP server in the chat/agent.

Do not configure ComfyUI as an LLM endpoint or MCP server. Image work must
remain a queued belt job so the worker owns VRAM, cards, retries, and review.
