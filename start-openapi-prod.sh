#!/usr/bin/env bash
# macOS/Linux equivalent of start-openapi-prod.cmd
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AIS_OPENAPI_MODE=production
exec "$SCRIPT_DIR/start-openapi-test.sh" /prod
