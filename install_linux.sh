#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,13), "Use Python 3.11 or 3.12"; import tkinter'
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m jailwatch download-model
.venv/bin/python -m unittest discover -s tests -v
echo 'Installed. Run: .venv/bin/python -m jailwatch gui'
