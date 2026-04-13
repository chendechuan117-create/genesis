FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    git bash tar findutils coreutils \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /workspace
WORKDIR /workspace
