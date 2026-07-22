@echo off
setlocal
REM Run this on the target Windows PC after installing Python 3 and PyInstaller.
for /f %%v in ('python bump_build_version.py') do set BUILD_VERSION=%%v
echo Building B518 Upper Computer Simulator V%BUILD_VERSION%
python -m PyInstaller --noconfirm --clean --windowed --name "B518 Upper Computer Simulator" upper_computer_simulator.py
echo.
echo Built V%BUILD_VERSION%: dist\B518 Upper Computer Simulator\B518 Upper Computer Simulator.exe
