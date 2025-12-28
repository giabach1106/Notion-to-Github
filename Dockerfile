FROM python:3.11-slim

# Install git and necessary tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create directory for SSH keys
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh

# Configure SSH to use ed25519 key
RUN echo "Host github.com\n\tHostName github.com\n\tIdentityFile /root/.ssh/id_ed25519\n\tStrictHostKeyChecking no\n\tUserKnownHostsFile=/dev/null" > /root/.ssh/config && \
    chmod 600 /root/.ssh/config

# Configure git to use SSH instead of HTTPS for github.com
RUN git config --global url."git@github.com:".insteadOf "https://github.com/"

# Run the main script
CMD ["python", "-u", "main.py"]