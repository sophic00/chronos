# ---- Base Stage ----
FROM python:3.11-slim-bookworm as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app


# ---- Builder Stage ----
FROM base as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ---- Final Stage ----
FROM base as final

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy the application source code
COPY . .

# The command to run when the container starts
CMD ["python", "-u", "main.py"] 