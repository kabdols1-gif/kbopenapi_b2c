#!/usr/bin/env bash
# macOS/Linux equivalent of start-openapi-dev.cmd
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AIS_OPENAPI_MODE=development
exec "$SCRIPT_DIR/start-openapi-test.sh" /dev
