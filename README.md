# SFTP endpoint probe

Periodically checks whether the configured server and port accept a TCP connection. This checks network reachability only; it does not perform an SSH handshake or authenticate to SFTP.

## Setup

```bash
python -m pip install -r requirements.txt
```

Copy `config.example.yaml` to `config.yaml` and replace the example hosts. Each entry under `servers` requires:

- `servername`: DNS name or IP address
- `port`: TCP port, commonly `22`
- `interval`: seconds between probe starts for that server

The optional top-level `timeout` sets the connection timeout in seconds (default: `5`).

## Run

```bash
python sftp_probe.py config.yaml
```

Use `--once` to probe each server once and exit with a non-zero status if any connection fails:

```bash
python sftp_probe.py config.yaml --once
```