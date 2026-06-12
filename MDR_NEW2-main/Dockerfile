# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Set work directory
WORKDIR /app

# Install system dependencies (needed for OpenCV and basic utilities)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Create necessary directories for uploads, logs and reports
RUN mkdir -p /app/logs /app/uploads/patients /app/uploads/frames /app/uploads/reports

# Expose the Flask port
EXPOSE 5000

# Start the application using Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:create_app()"]
