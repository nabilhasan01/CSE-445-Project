FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    g++ \
    nodejs \
    openjdk-17-jdk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sandbox

CMD ["tail", "-f", "/dev/null"]
