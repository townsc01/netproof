FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata python3 jq coreutils iputils-ping curl gnupg \
  && rm -rf /var/lib/apt/lists/*

# Ookla Speedtest CLI repo + install
RUN mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://packagecloud.io/ookla/speedtest-cli/gpgkey \
     | gpg --dearmor -o /etc/apt/keyrings/ookla-speedtest.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/ookla-speedtest.gpg] https://packagecloud.io/ookla/speedtest-cli/debian/ bookworm main" \
     > /etc/apt/sources.list.d/ookla-speedtest.list \
  && apt-get update \
  && apt-get install -y --no-install-recommends speedtest \
  && rm -rf /var/lib/apt/lists/*

# iperf3 stays optional (only needed in MODE=iperf)
RUN apt-get update && apt-get install -y --no-install-recommends iperf3 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY entrypoint.sh wizard.sh /app/
COPY scripts/ /app/scripts/
RUN chmod +x /app/entrypoint.sh /app/wizard.sh /app/scripts/*.sh

ENTRYPOINT ["/app/entrypoint.sh"]
