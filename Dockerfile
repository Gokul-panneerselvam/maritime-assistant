FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency specifications
COPY pyproject.toml uv.lock* ./

# Install project dependencies
RUN uv pip install --system -r pyproject.toml

# Copy project source
COPY . .

# Expose ports for FastAPI gateway and FastMCP server
EXPOSE 8080 8000

# Default entry point
CMD ["python", "-m", "ai_agent.src.api.main"]

