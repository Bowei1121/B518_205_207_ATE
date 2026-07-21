@echo off
setlocal
REM Run this on the target Windows PC after installing Python 3 and PyInstaller.
python -m PyInstaller --noconfirm --clean --windowed --name "B518 Upper Computer Simulator" upper_computer_simulator.py
echo.
echo Built: dist\B518 Upper Computer Simulator\B518 Upper Computer Simulator.exe
