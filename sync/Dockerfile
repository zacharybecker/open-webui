FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the sync script
COPY confluence_sync.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "confluence_sync.py", "--help"]