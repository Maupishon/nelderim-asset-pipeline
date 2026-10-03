#!/usr/bin/env bash
# Starts Nelderim Lab (the one app: hub + pipeline). Same as run_nelderim.sh.
cd "$(dirname "${BASH_SOURCE[0]}")"
exec bash ./run_nelderim.sh
