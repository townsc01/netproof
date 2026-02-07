FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iperf3 iputils-ping ca-certificates tzdata python3 jq coreutils \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY entrypoint.sh wizard.sh /app/
COPY scripts/ /app/scripts/
RUN chmod +x /app/entrypoint.sh /app/wizard.sh /app/scripts/*.sh

ENTRYPOINT ["/app/entrypoint.sh"]
