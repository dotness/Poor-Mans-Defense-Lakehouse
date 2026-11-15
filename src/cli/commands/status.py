import socket
import json
import subprocess
from typing import Dict, Any
from tabulate import tabulate

try:
    from src.config.settings import settings
    from src.cli.commands.login import require_cli_auth
except ImportError:
    from config.settings import settings
    from cli.commands.login import require_cli_auth

CORE_SERVICES = [
    ("traefik", "localhost", settings.traefik_dashboard_port),
    ("mosquitto", settings.mqtt_host, settings.mqtt_port),
    ("minio", settings.minio_endpoint.split(":")[0], int(settings.minio_endpoint.split(":")[1])),
    ("postgres", settings.postgres_host, settings.postgres_port),
    ("redis", settings.redis_host, settings.redis_port),
    ("memgraph", settings.memgraph_host, settings.memgraph_port),
    ("temporal", settings.temporal_host, settings.temporal_port),
]

OPTIONAL_SERVICES = [
    ("spiderfoot", settings.spiderfoot_host, settings.spiderfoot_port),
]


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    hosts_to_try = [host]
    if host in ("localhost", "127.0.0.1") and "127.0.1.1" not in hosts_to_try:
        hosts_to_try.append("127.0.1.1")
    for h in hosts_to_try:
        try:
            with socket.create_connection((h, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return False


def get_docker_stats() -> Dict[str, str]:
    stats = {}
    try:
        res = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}:{{.MemUsage}}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            for line in res.stdout.strip().split("\n"):
                if ":" in line:
                    parts = line.split(":")
                    stats[parts[0].strip()] = parts[1].strip()
    except Exception:
        pass
    return stats


def find_container_memory(service_name: str, docker_stats: Dict[str, str]) -> str:
    artemis_key = f"artemis-{service_name}"
    if artemis_key in docker_stats:
        return docker_stats[artemis_key]
    if service_name in docker_stats:
        return docker_stats[service_name]
    for c_name, usage in docker_stats.items():
        if c_name.endswith(f"_{service_name}") or c_name.endswith(f"-{service_name}"):
            return usage
    for c_name, usage in docker_stats.items():
        if service_name in c_name:
            return usage
    return "N/A"


def run_status(json_mode: bool = False) -> int:
    require_cli_auth(json_mode=json_mode)
    docker_stats = get_docker_stats()
    results = {}
    table_data = []
    overall_healthy = True

    for name, host, port in CORE_SERVICES:
        is_up = check_port(host, port)
        if not is_up:
            overall_healthy = False
        status_str = "HEALTHY" if is_up else "UNREACHABLE"
        mem_usage = find_container_memory(name, docker_stats)

        results[name] = {
            "status": status_str,
            "host": host,
            "port": port,
            "memory": mem_usage,
            "type": "core",
        }
        table_data.append([name, status_str, f"{host}:{port}", mem_usage])

    for name, host, port in OPTIONAL_SERVICES:
        is_up = check_port(host, port)
        status_str = "HEALTHY" if is_up else "STANDBY"
        mem_usage = find_container_memory(name, docker_stats)

        results[name] = {
            "status": status_str,
            "host": host,
            "port": port,
            "memory": mem_usage,
            "type": "optional",
        }
        table_data.append([f"{name} (opt)", status_str, f"{host}:{port}", mem_usage])

    if json_mode:
        print(json.dumps({
            "status": "HEALTHY" if overall_healthy else "DEGRADED",
            "services": results
        }, indent=2))
    else:
        print("\n=== Artemis Platform Health Status ===")
        print(tabulate(table_data, headers=["Service", "Status", "Endpoint", "Container Memory"], tablefmt="simple"))
        print("\nTarget Idle VM Budget: < 12GB RAM")
        if overall_healthy:
            print("Overall State: ALL SERVICES HEALTHY\n")
        else:
            print("Overall State: SOME SERVICES UNREACHABLE (Run 'make up' to start)\n")

    return 0 if overall_healthy else 1
