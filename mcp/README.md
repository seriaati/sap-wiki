# sap-mcp

Remote MCP server for Super Auto Pets game data.

## Run locally

```bash
# from sap-wiki/mcp/
SAP_DATA_DIR=../dumper/output uv run python -m sap_mcp
```

Serves at `http://localhost:8765/mcp`.

## Docker

```bash
docker build -f mcp/Dockerfile -t sap-mcp .
docker run --rm -p 8765:8765 sap-mcp
```

## Refresh data

After re-running the dumper:

```bash
docker build -t sap-mcp:latest .
docker compose up -d sap-mcp
```

## Tools

| Tool | Description |
|---|---|
| `list_pets` | Browse pets with tier/trigger/name/rollable filters |
| `get_pet` | Full pet record by slug or name |
| `list_foods` | Browse foods with tier/name/rollable filters |
| `get_food` | Full food record by slug or name |
| `list_toys` | Browse toys with tier/trigger/name/rollable filters |
| `get_toy` | Full toy record by slug or name |
| `search` | Full-text search across all entities |
| `get_stats` | Entity counts and server metadata |
