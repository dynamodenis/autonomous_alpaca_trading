FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y curl build-essential git && \
    rm -rf /var/lib/apt/lists/*

# Install uv and add to PATH immediately
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -s /root/.cargo/bin/uv /usr/local/bin/uv && \
    ln -s /root/.cargo/bin/uvx /usr/local/bin/uvx

# Verify uv installation
RUN uv --version

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Verify Node.js installation
RUN node --version && npm --version

# Copy files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p memory sandbox

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.cargo/bin:$PATH"

EXPOSE 7860

CMD ["python", "app.py"]