# ---- Base Stage ----
FROM python:3.12-slim-bookworm AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app


# ---- Builder Stage ----
FROM base AS builder

# Install uv and create a lockfile-exact virtualenv (dev deps excluded)
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# ---- Final Stage ----
FROM base AS final

# Reuse the resolved environment from the builder stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy the application source code
COPY . .

# The command to run when the container starts
CMD ["python", "-u", "-m", "chronos.main"]
