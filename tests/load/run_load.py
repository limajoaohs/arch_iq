"""Dispara N requisicoes simultaneas em POST /api/audit e resume o resultado.

So aceita 127.0.0.1 ou localhost: rodar isto contra producao gastaria a cota do
Bedrock e dispararia alertas SNS.

    python tests/load/run_load.py --url http://127.0.0.1:8099 --requests 1000
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from urllib.parse import urlparse

import aiohttp

TERRAFORM = """
resource "aws_security_group" "web" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web" {
  instance_type = "t3.medium"
}

resource "aws_s3_bucket" "uploads" {
  bucket = "uploads"
  acl    = "public-read"
}

resource "aws_db_instance" "app" {
  engine              = "postgres"
  storage_encrypted   = false
  publicly_accessible = true
}
"""


def percentile(ordered, fraction):
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


async def one_request(session, url, index, gate, results):
    await gate.wait()  # todas as requisicoes saem juntas
    started = time.perf_counter()
    try:
        async with session.post(url, json={"code_or_prompt": TERRAFORM, "session_id": f"load-{index}"}) as response:
            body = await response.read()
            valid = False
            if response.status == 200:
                data = json.loads(body)
                valid = (
                    data["session_id"] == f"load-{index}"
                    and bool(data["client_report"]["risks"])
                    and bool(data["layperson_explanation"])
                )
            results.append((response.status, time.perf_counter() - started, valid, time.perf_counter()))
    except Exception as error:
        results.append((type(error).__name__, time.perf_counter() - started, False, time.perf_counter()))


async def probe_health(session, url, stop, probes):
    """Mede o /health durante a carga: e o que o Render usa para saber se o servico esta vivo."""
    while not stop.is_set():
        started = time.perf_counter()
        try:
            async with session.get(url) as response:
                await response.read()
                probes.append(time.perf_counter() - started)
        except Exception:
            probes.append(float("inf"))
        await asyncio.sleep(1)


async def run(base_url, total, timeout):
    results = []
    probes = []
    gate = asyncio.Event()
    stop_probe = asyncio.Event()
    connector = aiohttp.TCPConnector(limit=0, force_close=True)
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
        tasks = [
            asyncio.create_task(one_request(session, f"{base_url}/api/audit", i, gate, results))
            for i in range(total)
        ]
        await asyncio.sleep(0.2)
        started = time.perf_counter()
        gate.set()
        probe = asyncio.create_task(probe_health(session, f"{base_url}/health", stop_probe, probes))
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - started
        stop_probe.set()
        await probe

        async with session.get(f"{base_url}/__load/counts") as response:
            counts = await response.json() if response.status == 200 else {}
    finished = sorted(r[3] - started for r in results)
    return results, elapsed, counts, finished, probes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8099")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--timeout", type=float, default=300)
    options = parser.parse_args()

    if urlparse(options.url).hostname not in ("127.0.0.1", "localhost"):
        sys.exit("Este teste so roda localmente, para nao gastar a cota do Bedrock.")

    results, elapsed, counts, finished, probes = asyncio.run(
        run(options.url.rstrip("/"), options.requests, options.timeout)
    )
    latencies = sorted(r[1] for r in results)
    summary = {
        "requests": options.requests,
        "ok_valid": sum(1 for r in results if r[2]),
        "status": {str(k): v for k, v in Counter(r[0] for r in results).items()},
        "total_seconds": round(elapsed, 2),
        "throughput_rps": round(options.requests / elapsed, 1),
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 3),
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(percentile(latencies, 0.95), 3),
            "p99": round(percentile(latencies, 0.99), 3),
            "max": round(latencies[-1], 3),
        },
        "finished_by_percent": {f"{p}%": round(percentile(finished, p / 100), 2) for p in (10, 25, 50, 75, 90)},
        "health_during_load": {
            "probes": len(probes),
            "worst_seconds": round(max(probes), 3) if probes else None,
            "median_seconds": round(statistics.median(probes), 3) if probes else None,
        },
        "simulated_calls": counts,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok_valid"] == options.requests else 1


if __name__ == "__main__":
    sys.exit(main())
