#!/usr/bin/env python3
"""Periodically check TCP reachability of configured SFTP endpoints."""

import argparse
import logging
import math
import socket
import threading
import time

import yaml


logger = logging.getLogger("sftp_probe")


def load_config(path):
    try:
        with open(path, encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"cannot read config: {error}") from error

    if not isinstance(config, dict):
        raise ValueError("config must be a YAML mapping")

    timeout = config.get("timeout", 5)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive number")

    servers = config.get("servers")
    if not isinstance(servers, list) or not servers:
        raise ValueError("servers must be a non-empty list")

    for index, server in enumerate(servers):
        label = f"servers[{index}]"
        if not isinstance(server, dict):
            raise ValueError(f"{label} must be a mapping")

        name = server.get("servername")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}.servername must be a non-empty string")

        port = server.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"{label}.port must be an integer from 1 to 65535")

        interval = server.get("interval")
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError(f"{label}.interval must be a positive number of seconds")

    return servers, float(timeout)


def probe(server, timeout):
    name = server["servername"]
    port = server["port"]
    started = time.monotonic()
    try:
        with socket.create_connection((name, port), timeout=timeout) as connection:
            with connection.makefile("rb") as reader:
                banner = read_ssh_banner(reader)
            elapsed = time.monotonic() - started
            logger.info("SSH banner %s:%d %r (%.3fs)", name, port, banner, elapsed)
            return True
    except OSError as error:
        elapsed = time.monotonic() - started
        logger.warning("SSH probe failed %s:%d after %.3fs: %s", name, port, elapsed, error)
        return False


def read_ssh_banner(reader):
    for _ in range(51):
        line = reader.readline(256)
        if not line:
            raise OSError("connection closed before SSH banner")
        if len(line) > 255 or not line.endswith(b"\n"):
            raise OSError("SSH banner line exceeds 255 bytes")

        banner = line.rstrip(b"\r\n").decode("ascii", errors="replace")
        if banner.startswith("SSH-"):
            return banner

    raise OSError("too many pre-banner lines without an SSH banner")


def watch_server(server, timeout, stop_event):
    interval = float(server["interval"])
    while not stop_event.is_set():
        started = time.monotonic()
        probe(server, timeout)
        stop_event.wait(max(0, interval - (time.monotonic() - started)))


def main():
    parser = argparse.ArgumentParser(description="Periodically probe configured SFTP server ports.")
    parser.add_argument("config", help="path to YAML configuration")
    parser.add_argument("--once", action="store_true", help="probe each server once and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        servers, timeout = load_config(args.config)
    except ValueError as error:
        parser.error(str(error))

    if args.once:
        results = [probe(server, timeout) for server in servers]
        return 0 if all(results) else 1

    stop_event = threading.Event()
    workers = [
        threading.Thread(target=watch_server, args=(server, timeout, stop_event), daemon=True)
        for server in servers
    ]
    for worker in workers:
        worker.start()

    try:
        while any(worker.is_alive() for worker in workers):
            for worker in workers:
                worker.join(timeout=0.5)
    except KeyboardInterrupt:
        logger.info("stopping probes")
        stop_event.set()
        for worker in workers:
            worker.join()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())