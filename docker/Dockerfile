FROM python:3.11-slim

# Prevent python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries and their system dependencies
RUN playwright install chromium --with-deps

# Copy application source
COPY app/ app/
COPY .env .env

# FastMCP defaults to running over stdio. 
# This command runs the server ready to communicate with host AI agents.
CMD ["python", "-m", "app.server.main"]
