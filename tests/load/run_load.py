"""Dispara N requisicoes simultaneas na API e resume o resultado.

Cenarios (--scenario):
  audit  todas em POST /api/audit (padrao)
  ask    todas em POST /api/ask, cada uma com uma pergunta diferente (sem cache)
  mixed  40% auditorias, 40% perguntas e 20% carregamentos da pagina (GET /)

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


QUESTIONS = [
    "O que devo resolver primeiro?",
    "Meu sistema esta seguro?",
    "Como posso gastar menos?",
    "O que essa nota quer dizer?",
]


def kind_for(scenario, index):
    if scenario != "mixed":
        return scenario
    return ("audit", "audit", "ask", "ask", "page")[index % 5]


def check_audit(data, index):
    return (
        data["session_id"] == f"load-{index}"
        and bool(data["client_report"]["risks"])
        and bool(data["layperson_explanation"])
    )


async def one_request(session, base_url, kind, index, gate, results):
    await gate.wait()  # todas as requisicoes saem juntas
    started = time.perf_counter()
    try:
        if kind == "page":
            request = session.get(f"{base_url}/")
        elif kind == "ask":
            # Pergunta unica por requisicao: o cache do agente nao pode mascarar a carga
            question = f"{QUESTIONS[index % len(QUESTIONS)]} (#{index})"
            request = session.post(f"{base_url}/api/ask", json={"code_or_prompt": TERRAFORM, "question": question})
        else:
            request = session.post(f"{base_url}/api/audit", json={"code_or_prompt": TERRAFORM, "session_id": f"load-{index}"})
        async with request as response:
            body = await response.read()
            valid = False
            if response.status == 200:
                if kind == "page":
                    valid = b'id="askForm"' in body
                elif kind == "ask":
                    valid = bool(json.loads(body)["answer"])
                else:
                    valid = check_audit(json.loads(body), index)
            results.append((response.status, time.perf_counter() - started, valid, time.perf_counter(), kind))
    except Exception as error:
        results.append((type(error).__name__, time.perf_counter() - started, False, time.perf_counter(), kind))


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


async def run(base_url, total, timeout, scenario):
    results = []
    probes = []
    gate = asyncio.Event()
    stop_probe = asyncio.Event()
    connector = aiohttp.TCPConnector(limit=0, force_close=True)
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
        tasks = [
            asyncio.create_task(one_request(session, base_url, kind_for(scenario, i), i, gate, results))
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
    parser.add_argument("--scenario", choices=("audit", "ask", "mixed"), default="audit")
    options = parser.parse_args()

    if urlparse(options.url).hostname not in ("127.0.0.1", "localhost"):
        sys.exit("Este teste so roda localmente, para nao gastar a cota do Bedrock.")

    results, elapsed, counts, finished, probes = asyncio.run(
        run(options.url.rstrip("/"), options.requests, options.timeout, options.scenario)
    )
    latencies = sorted(r[1] for r in results)
    by_kind = {}
    for kind in sorted({r[4] for r in results}):
        rows = sorted(r[1] for r in results if r[4] == kind)
        by_kind[kind] = {
            "requests": len(rows),
            "ok_valid": sum(1 for r in results if r[4] == kind and r[2]),
            "p50": round(percentile(rows, 0.50), 3),
            "p95": round(percentile(rows, 0.95), 3),
            "max": round(rows[-1], 3),
        }
    summary = {
        "scenario": options.scenario,
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
        "by_kind": by_kind,
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
