@echo off
REM One-click test runner: installs dependencies and runs pytest
python -m pip install -r requirements.txt
python -m pytest -q
