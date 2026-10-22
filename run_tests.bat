@echo off
REM Run the pytest suite for the Tax Rules & Evidence Engine
cd /d %~dp0
if exist .venv\Scripts\activate call .venv\Scripts\activate
set TAXENGINE_DATA_DIR=%~dp0data_test
set PYTHONPATH=%~dp0src
python -m pytest tests/ -q
pause
