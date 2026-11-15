FROM python:3.12-slim

WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install analytical runtime requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create standard input/output/script mount points
RUN mkdir -p /workspace/input /workspace/output /workspace/script

# Set default entrypoint to execute user script
ENTRYPOINT ["python", "/workspace/main.py"]
