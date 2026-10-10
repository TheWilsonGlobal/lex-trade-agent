# Sandboxed Container for lex-trade-agent
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Install essential runtime dependencies & security utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

# Install Python package dependencies
COPY pyproject.toml ${APP_HOME}/
RUN pip install --upgrade pip setuptools wheel && \
    pip install pydantic mcp httpx numpy streamlit python-dotenv pytest pytest-asyncio

# Copy project source code
COPY . ${APP_HOME}/

# Fix ownership
RUN chown -R appuser:appgroup ${APP_HOME}

# Switch to unprivileged sandbox user
USER appuser

# Healthcheck verifying MCP server or agent import
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "from src.mcp_servers.compliance_mcp import screen_entity; print('healthy')" || exit 1

EXPOSE 8000 8501

# Default entrypoint runs the end-to-end CLI demonstration
CMD ["python", "-m", "src.agent.hermes_orchestrator"]
