@echo off
REM Install dependencies
pip install -r requirements.txt

REM Run tests
python -m pytest tests/ -v