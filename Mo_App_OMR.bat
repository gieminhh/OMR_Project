@echo off
cd /d "%~dp0"
title Khoi chay OMR Scanner GUI
echo Dang khoi dong ung dung OMR Scanner...
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" run_simple_gui.py
) else (
    start "" python run_simple_gui.py
)
exit
