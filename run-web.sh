#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if curl -fsS http://127.0.0.1:8765/__version >/dev/null 2>&1; then
    echo 'Port 8765 is occupied. Close the other Quantru server before starting this one.'
    exit 1
fi
exec python3 -B -u server.py
