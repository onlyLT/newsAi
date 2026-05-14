@echo off
REM Double-click to start the newsAi web dashboard.
REM Opens browser to http://localhost:8765 and keeps uvicorn running in this window.
REM Close this window to stop the dashboard.

cd /d E:\dev\newsAi
start "" http://localhost:8765
.\.venv\Scripts\python.exe -m uvicorn web.main:app --port 8765 --host 127.0.0.1
