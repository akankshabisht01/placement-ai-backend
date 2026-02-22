# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy essential application files explicitly
COPY app.py .
COPY chatbot_api.py .
COPY domain_keywords.py .
COPY loading_questions_api.py .
COPY *.pkl ./

# Copy package directories
COPY models/ ./models/
COPY data/ ./data/
COPY utils/ ./utils/
COPY templates/ ./templates/
COPY routes/ ./routes/

# Debug: List what was copied
RUN echo "=== Contents of /app ===" && ls -la /app/ && \
    echo "=== Contents of /app/models ===" && ls -la /app/models/ && \
    echo "=== Contents of /app/data ===" && ls -la /app/data/ && \
    echo "=== Contents of /app/utils ===" && ls -la /app/utils/ && \
    echo "=== Contents of /app/routes ===" && ls -la /app/routes/

# Expose port
EXPOSE 8080

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120", "app:app"]
