FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy project definition and source
COPY pyproject.toml ./
COPY src/ src/

# Install core + dev dependencies
RUN uv pip install --system --no-cache -e ".[dev]"

# Copy tests and pytest config
COPY tests/ tests/
COPY docker/pytest.ini pytest.ini

# Default: run unit tests
CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
