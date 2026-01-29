FROM python:3.13.0-bullseye
WORKDIR /source

# Upgrade pip and install uv
RUN pip install --upgrade pip
RUN pip install uv

# Copy application code
COPY . .

# Install the current project after copying all files
RUN uv sync

EXPOSE 8000

CMD uv run server.py