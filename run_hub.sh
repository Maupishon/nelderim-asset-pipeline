#!/usr/bin/env bash
cd "$(dirname "${BASH_SOURCE[0]}")"
for p in python3 python; do command -v "$p" >/dev/null && exec "$p" nelderim_hub.py; done
echo "Python 3.10+ not found."; read -r -p "Enter to close..." _
