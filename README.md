# NetProof

NetProof is a simple Docker tool that helps you prove internet slowdowns/dropouts by generating an ISP-ready evidence pack.

It measures:
- Throughput (download + upload) to a VPS you control (iperf3)
- Ping to your router (LAN/Wi-Fi health)
- Ping to the internet (WAN/ISP health)

At the end, it generates:
- isp_summary.txt (human readable)
- bullshit_events.csv (worst incidents)
- plus supporting CSVs

## What you need

1) A machine that can run Docker (NAS, Linux box, Mac/Windows with Docker).
2) A VPS on the internet (DigitalOcean/Linode/Vultr/etc).

## Step 1: Set up iperf3 server on your VPS

SSH into your VPS, then run:

    sudo apt update
    sudo apt install -y iperf3
    nohup iperf3 -s > /root/iperf_server.log 2>&1 &

(Optional) Confirm it’s running:

    ps aux | grep iperf3

## Step 2: Make a folder for NetProof data

On the machine where you’ll run NetProof:

    mkdir -p netproof_data

This folder will store logs and output CSVs.

## Step 3: Run the setup wizard

This writes config into netproof_data/config.env:

    docker run --rm -it -v $PWD/netproof_data:/data ghcr.io/townsc01/netproof:latest wizard

## Step 4: Start logging (overnight)

Run in the background:

    docker run -d --name netproof --restart unless-stopped -v $PWD/netproof_data:/data ghcr.io/townsc01/netproof:latest run

Check it’s running:

    docker ps

View logs:

    docker logs -f netproof

## Step 5: Stop logging

    docker stop netproof
    docker rm netproof

## Step 6: Generate the ISP report pack

    docker run --rm -v $PWD/netproof_data:/data ghcr.io/townsc01/netproof:latest report

## Output files (in netproof_data)

- isp_summary.txt
- bullshit_events.csv
- iperf_summary.csv
- ping_router.csv
- ping_external.csv

Raw logs:
- iperf_log.ndjson
- iperf_err.log
- ping_router.txt
- ping_external.txt

## Typical workflow

1) Run overnight
2) Generate report in the morning
3) Email your ISP: isp_summary.txt + bullshit_events.csv + iperf_summary.csv + ping_external.csv

If router ping is clean but external ping + throughput is bad, your ISP can’t blame your Wi-Fi.

