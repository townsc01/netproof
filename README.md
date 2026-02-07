# NetProof

NetProof is a Docker tool that helps you prove internet slowdowns/dropouts by generating an ISP-ready evidence pack.

It measures:
- Speed (download/upload) using Ookla Speedtest (no VPS needed)
- Ping to your router (LAN/Wi-Fi health)
- Ping to the internet (WAN/ISP health)

It outputs a single integrated CSV aligned by timestamp:
- unified_timeseries.csv
Plus:
- isp_summary.txt

## Two modes

A) Easy mode (recommended): Ookla Speedtest (NO VPS)
- Default mode. Cheapest and simplest.

B) Advanced mode: iperf3 to your own VPS
- More controlled, but requires a VPS and an iperf3 server.
- If your iperf server is shared/overloaded you may see “server is busy”.

## Quick start (easy mode: no VPS)

1) Create a folder for logs/output:

    mkdir -p netproof_data

2) Run the wizard and choose speedtest (default):

    docker run --rm -it -v $PWD/netproof_data:/data ghcr.io/townsc01/netproof:latest wizard

3) Start logging (background):

    docker run -d --name netproof --restart unless-stopped -v $PWD/netproof_data:/data ghcr.io/townsc01/netproof:latest run

4) Generate the report:

    docker run --rm -v $PWD/netproof_data:/data ghcr.io/townsc01/netproof:latest report

Outputs appear in netproof_data/.

## Advanced mode (iperf3 + VPS)

1) On your VPS:

    sudo apt update
    sudo apt install -y iperf3
    nohup iperf3 -s > /root/iperf_server.log 2>&1 &

2) Run the wizard and choose iperf, then enter the VPS IP.

## Output files (netproof_data)

Main:
- unified_timeseries.csv

Summary:
- isp_summary.txt

Raw logs:
- speed_log.ndjson (speedtest mode)
- iperf_log.ndjson (iperf mode)
- ping_router.txt
- ping_external.txt
