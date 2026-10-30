#!/bin/bash
cd "$(dirname "$0")"
pip install -q -r requirements.txt
[ -f dist/stub ] || python3 -m PyInstaller --onefile --console stub.py >/dev/null 2>&1
python3 detector.py &
python3 painel.py
