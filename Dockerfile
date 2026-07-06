FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /data

# Expose ports
EXPOSE 6667 8080

# Volume for persistent data
VOLUME ["/data"]

# Run BNC
CMD ["python", "-m", "irc_bnc.main", "--config", "/data/config.json"]