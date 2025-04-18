# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed (optional, add if specific libraries require them)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install Poetry (if using Poetry for dependency management - adjust if using requirements.txt)
# RUN pip install poetry

# Copy dependency definition file(s)
COPY requirements.txt .
# If using Poetry:
# COPY pyproject.toml poetry.lock* ./

# Add a cache-busting argument (e.g., current date or a version number)
# This ensures the RUN pip install layer is rebuilt if this line changes
ARG CACHEBUST=1

# Install dependencies
# --no-cache-dir prevents caching which is good for image size but slower for rebuilds during dev
RUN pip install --no-cache-dir -r requirements.txt

# Add a step to list the contents of the bin directory to verify gunicorn exists
RUN ls -l /usr/local/bin

# If using Poetry:
# RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-dev

# Copy the rest of the application code into the working directory
# Ensure .dockerignore is configured properly to exclude unnecessary files (.git, .venv, etc.)
COPY . .

# Expose the port Gunicorn will listen on (Railway provides this via $PORT)
# We don't strictly need EXPOSE when using Railway's $PORT, but it's good practice
# Gunicorn will bind to the port specified in the CMD
# EXPOSE 7860 # Remove old Gradio expose

# Define the command to run the application using Gunicorn with absolute path
# Gunicorn will bind to 0.0.0.0 and the port specified by the $PORT environment variable
# agency:app tells gunicorn to look for the 'app' object inside the 'agency.py' file
# Increase timeout to handle potentially long Gradio/Agency Swarm startup
CMD ["/usr/local/bin/gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--threads", "8", "--timeout", "120", "agency:app"] 