#!/bin/bash
# Ponto de entrada no Lambda: a camada Lambda Web Adapter repassa cada requisicao para o uvicorn nesta porta.
export PATH="$PATH:$LAMBDA_TASK_ROOT/bin"
export PYTHONPATH="$LAMBDA_TASK_ROOT:$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR"
exec python -m uvicorn src.api.app:app --host 127.0.0.1 --port "$PORT"
