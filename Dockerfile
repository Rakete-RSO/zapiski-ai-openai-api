# Use the official Python image as a base
FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
 \
    # Set the working directory inside the container
WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy only the Poetry files first to leverage Docker's caching
COPY poetry.lock pyproject.toml /app/

# Install dependencies using Poetry (without virtualenvs, as we are in a container)
RUN poetry config virtualenvs.create false && poetry install --only main

# Copy the rest of the application files
COPY . /app

# Copy .env file into the container (optional: or load it dynamically)
RUN cp .example.env .env

# Expose the port for the FastAPI server
EXPOSE 8000

# Command to run the FastAPI server
CMD ["poetry", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
