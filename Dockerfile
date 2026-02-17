# Use a slim Python image for a smaller footprint
FROM python:3.10-slim

# Set the working directory
WORKDIR /code

# Install system dependencies (needed for some PDF processing tools)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Create a non-root user for Hugging Face security
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Copy the application code
WORKDIR $HOME/app
COPY --chown=user . $HOME/app

# Hugging Face Spaces uses port 7860 by default
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]