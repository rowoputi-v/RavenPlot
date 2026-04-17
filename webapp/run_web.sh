#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Starting Raven Plot web app at http://localhost:5050"
"$DIR/../.venv/bin/python" "$DIR/app.py"
