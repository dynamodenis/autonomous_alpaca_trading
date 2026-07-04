FROM python:3.12-slim

# System dependencies + Node.js (npx-based MCP servers: tavily, memory-libsql)
RUN apt-get update && \
    apt-get install -y curl build-essential git && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces runs the container as UID 1000, so everything the app
# touches (pip packages, uv/uvx caches, SQLite files, memory/) must live under
# a home owned by that user — root-owned paths fail at runtime on Spaces.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user
ENV PATH="/home/user/.local/bin:$PATH"
WORKDIR /home/user/app

# Install uv/uvx for the runtime user (MCP servers are spawned via `uv run`)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && uv --version

COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user:user . .

# Create necessary directories
RUN mkdir -p memory sandbox

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Serve the FastAPI backend. Run from the app dir so the MCP servers'
# cwd-relative paths (uv run *.py, file:./memory/{name}.db) resolve correctly.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
