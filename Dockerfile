# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies with cache cleanup
RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf ~/.cache/pip

# Copy application code
COPY app.py .
COPY models/ ./models/
COPY data/ ./data/
COPY utils/ ./utils/
COPY templates/ ./templates/
COPY *.pkl ./

# Expose port
EXPOSE 8080

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
