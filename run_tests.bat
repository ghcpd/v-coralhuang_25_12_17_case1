@echo off
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest -q
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo All tests ran.