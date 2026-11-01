FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 build-essential binutils git curl ca-certificates xz-utils pkg-config \
    libssl-dev zlib1g-dev libncurses-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY . .
CMD ["python3", "scripts/reproduce.py", "standalone"]
