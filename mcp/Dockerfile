# syntax=docker/dockerfile:1.7
# Build context must be repo root: docker build -f mcp/Dockerfile -t sap-mcp .

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build
WORKDIR /app
COPY mcp/pyproject.toml ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project
COPY mcp/sap_mcp ./sap_mcp
RUN uv sync --no-dev

FROM python:3.14-slim
WORKDIR /app
COPY --from=build /app /app
COPY dumper/output /data
ENV SAP_DATA_DIR=/data
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8765
CMD ["python", "-m", "sap_mcp"]
