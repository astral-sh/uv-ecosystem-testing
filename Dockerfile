FROM ghcr.io/astral-sh/uv:debian-slim AS builder

ENV UV_COMPILE_BYTECODE=1
WORKDIR /app

RUN uv python install 3.14

COPY pyproject.toml uv.lock Readme.md ./
RUN uv sync -p 3.14 --locked --no-install-project
COPY src/ src/
RUN uv sync -p 3.14 --locked --no-editable

FROM ghcr.io/astral-sh/uv:debian-slim AS runtime

RUN uv python install 3.14

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY data/ data/

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["/app/.venv/bin/python", "-m", "uv_ecosystem_testing.run"]