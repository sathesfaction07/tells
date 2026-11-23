#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────────────────────────────────────
# Tells Setup Script
# Detects OS, creates/reuses virtual environment, installs dependencies.
# No cloud provisioning needed — this tool runs locally against a running
# Chrome instance.
# ─────────────────────────────────────────────────────────────────────────────

VENV_DIR=".venv"
PYTHON_MIN="3.11"

detect_os() {
    case "$(uname -s)" in
        Linux*)   OS="linux" ;;
        Darwin*)  OS="macos" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)        OS="unknown" ;;
    esac
    echo "Detected OS: $OS"
}

find_python() {
    for cmd in python3.12 python3.11 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+' || "$cmd" -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            PYTHON="$cmd"
            echo "Using Python: $PYTHON ($version)"
            return 0
        fi
    done
    echo "ERROR: Python >= $PYTHON_MIN not found."
    exit 1
}

setup_venv() {
    if [ -d "$VENV_DIR" ]; then
        echo "Virtual environment exists — reusing."
    else
        echo "Creating virtual environment..."
        $PYTHON -m venv "$VENV_DIR"
    fi

    if [ "$OS" = "windows" ]; then
        source "$VENV_DIR/Scripts/activate"
    else
        source "$VENV_DIR/bin/activate"
    fi

    pip install --upgrade pip --quiet
    pip install -e ".[dev]" --quiet
    echo "Dependencies installed."
}

run_app() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Tells is ready."
    echo ""
    echo "  Prerequisites:"
    echo "    Chrome running with: google-chrome --remote-debugging-port=9222"
    echo ""
    echo "  Usage:"
    echo "    tells products.csv --output results/"
    echo "    tells products.csv --llm --brief --output results/"
    echo "═══════════════════════════════════════════════════════════════"
}

main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║            Tells — Setup                             ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""
    detect_os
    find_python
    setup_venv
    run_app
}

main "$@"
