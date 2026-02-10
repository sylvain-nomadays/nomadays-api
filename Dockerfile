FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway assigns PORT dynamically)
EXPOSE ${PORT:-8000}

# Run the application (use PORT env var from Railway, default to 8000)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
