# Use the full official Python runtime as a parent image
FROM python:3.11

# Add a build argument that can be changed to break the cache
ARG FORCE_REBUILD=3 # Increment this value to force a rebuild

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

# Remove the previous cache-busting ARG
# ARG CACHEBUST=1

# Install dependencies and immediately check for gunicorn in the same RUN step
RUN echo "Forcing rebuild with arg: ${FORCE_REBUILD}" && \
    pip install --no-cache-dir -r requirements.txt && \
    echo "Checking for gunicorn immediately after install:" && \
    pip show -f gunicorn

# Add a step to show where gunicorn's files (including scripts) were installed
# RUN pip show -f gunicorn # Combined into the step above

# Remove the diagnostic ls command
# RUN ls -l /usr/local/bin

# If using Poetry:
# RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-dev

# Copy the rest of the application code into the working directory
# Ensure .dockerignore is configured properly to exclude unnecessary files (.git, .venv, etc.)
COPY . .

# Expose the port Gunicorn will listen on (Railway provides this via $PORT)
# We don't strictly need EXPOSE when using Railway's $PORT, but it's good practice
# Gunicorn will bind to the port specified in the CMD
# EXPOSE 7860 # Remove old Gradio expose

# Define the command to run the application using Gunicorn
# Revert to just 'gunicorn' for now and rely on PATH
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "--threads", "8", "--timeout", "120", "agency:app"] 