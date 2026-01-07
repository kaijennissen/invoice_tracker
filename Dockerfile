# Stage 1: Builder
FROM python:3.13.7-slim-bookworm AS builder

# Set working directory
WORKDIR /app

# Install system dependencies needed for building Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock .python-version ./

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set environment variables for uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=python3.13 \
    UV_LINK_MODE=copy

# Install dependencies without the project itself
RUN uv sync \
    --frozen \
    --no-dev \
    --no-install-project

# Copy application code
COPY src/your_project_name ./src/your_project_name

# Install the project itself in non-editable mode
RUN uv sync \
    --frozen \
    --no-dev \
    --no-editable

# Stage 2: Final image
FROM python:3.13.7-slim-bookworm AS final

# Install runtime dependencies
RUN apt-get update && apt-get install -y libgomp1 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create logs directory
RUN mkdir -p /app/logs

# Copy application and virtual environment from builder
COPY --from=builder /app /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"

# Verify installation and run smoke test
RUN <<EOT
python -V
python -Im site
python -Ic 'import your_project_name'
EOT

# Define entrypoint
ENTRYPOINT ["python", "-m", "your_project_name"]
