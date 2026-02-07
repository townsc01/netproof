# NetProof

NetProof is a CLI-first Docker tool for logging internet instability (throughput + latency) and generating ISP-ready evidence packs.

It runs:
- iperf3 upload/download tests to a VPS you control
- ping to your router (LAN stability)
- ping to 1.1.1.1 (WAN stability)

Outputs CSV + summary files that can be emailed to your ISP.

## Requirements

1. A VPS with iperf3 server running:

    sudo apt update
    sudo apt install -y iperf3
    nohup iperf3 -s > /root/iperf_server.log 2>&1 &

2. Docker installed on your NAS / server / machine.

## Quick start

### 1) Run wizard

    docker run --rm -it -v $PWD/netproof_data:/data netproof wizard

### 2) Run logger

    docker run -d --name netproof --restart unless-stopped -v $PWD/netproof_data:/data netproof run

### 3) Generate ISP report

    docker exec netproof netproof report

Your output files will be in `netproof_data/`.

