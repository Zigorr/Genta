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

# Install dependencies
# --no-cache-dir prevents caching which is good for image size but slower for rebuilds during dev
# RUN pip install --no-cache-dir -r requirements.txt
# If using Poetry:
# RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-dev
RUN pip install --no-cache-dir -r requirements.txt


# Copy the rest of the application code into the working directory
# Ensure .dockerignore is configured properly to exclude unnecessary files (.git, .venv, etc.)
COPY . .

# Expose the port the app runs on (Gradio default is 7860)
EXPOSE 7860

# Define the command to run the application
# Ensure agency.py is executable if needed (though usually not necessary for python scripts)
CMD ["python", "agency.py"] 