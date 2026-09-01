# Must match .python-version and the local venv: the pinned dependency set in
# requirements.txt is resolved for CPython 3.14 (cp314 wheels).
FROM python:3.14-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps first for layer caching.
# `--only-binary=:all:` makes the build fail loudly if a wheel is ever missing
# for this platform, instead of silently falling back to a source build (which
# is why no compiler toolchain is installed here). Every pin in the lock file
# has a cp314 manylinux wheel today.
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# Copy app source
COPY . .

# Prepare seed data for initializing a persistent /app/data volume on first run.
# When a volume is mounted at /app/data, the baked-in /app/data is hidden, so we
# keep a copy at /opt/seed/data.
RUN mkdir -p /opt/seed \
    && cp -a /app/data /opt/seed/data

# Streamlit configuration
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501

ENTRYPOINT ["python", "/app/docker_entrypoint.py"]
