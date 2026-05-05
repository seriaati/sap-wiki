# syntax=docker/dockerfile:1.7
# Dokploy doesn't pass cloned repo as build context, so we clone it ourselves.

FROM alpine/git:latest AS repo
ARG CACHEBUST=1
RUN git clone --depth=1 https://github.com/seriaati/sap-wiki.git /repo

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build
WORKDIR /app
COPY --from=repo /repo/mcp/pyproject.toml ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project
COPY --from=repo /repo/mcp/sap_mcp ./sap_mcp
RUN uv sync --no-dev

FROM python:3.14-slim
WORKDIR /app
COPY --from=build /app /app
COPY --from=repo /repo/dumper/output /data
ENV SAP_DATA_DIR=/data
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8765
CMD ["python", "-m", "sap_mcp"]
