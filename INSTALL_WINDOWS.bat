@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "JAILWATCH_PYTHON="

if not exist ".venv\Scripts\python.exe" goto find_python
call :try_python "%~dp0.venv\Scripts\python.exe"
if defined JAILWATCH_PYTHON goto python_ready
echo The existing .venv needs 64-bit Python 3.11 or 3.12.
echo Rename that .venv folder, then run this installer again.
goto failed

:find_python
rem Check normal install folders even when PATH has not refreshed yet.
for %%V in (311 312) do (
    call :try_python "%LocalAppData%\Programs\Python\Python%%V\python.exe"
    if defined JAILWATCH_PYTHON goto python_ready
    call :try_python "%ProgramFiles%\Python%%V\python.exe"
    if defined JAILWATCH_PYTHON goto python_ready
)

rem Avoid the Windows Store placeholder when searching PATH.
for /f "delims=" %%P in ('where python.exe 2^>nul ^| findstr /v /i /l /c:"Microsoft\WindowsApps"') do (
    call :try_python "%%P"
    if defined JAILWATCH_PYTHON goto python_ready
)

rem The optional launcher can locate custom Python installations.
for %%V in (3.11 3.12) do (
    for /f "delims=" %%P in ('py -%%V -c "import sys; print(sys.executable)" 2^>nul') do (
        call :try_python "%%P"
        if defined JAILWATCH_PYTHON goto python_ready
    )
)
echo Python 3.11 or 3.12 64-bit was not found.
echo Install Python with Add python.exe to PATH, pip, and Tcl/Tk selected.
echo The py launcher is optional. Close this window and reopen this installer after setup.
goto failed

:python_ready
"%JAILWATCH_PYTHON%" -c "import sys; print('Detected Python ' + sys.version.split()[0] + ': ' + sys.executable)"
"%JAILWATCH_PYTHON%" -c "import tkinter, venv, ensurepip" >nul 2>&1
if errorlevel 1 goto missing_components
if /i "%~1"=="--check-python" exit /b 0
if not exist ".venv\Scripts\python.exe" "%JAILWATCH_PYTHON%" -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m jailwatch download-model
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 goto failed
echo Installation completed. Open START_WINDOWS.bat, then Camera setup.
pause
exit /b 0

:missing_components
echo Python was found, but required Python components are missing.
echo Open the Python installer, choose Modify, and include pip and tcl/tk and IDLE.
goto failed

:failed
echo Installation stopped. Review the error above and retry after fixing it.
if /i "%~1"=="--check-python" exit /b 1
pause
exit /b 1

:try_python
if not exist "%~1" exit /b 1
"%~1" -c "import struct, sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "JAILWATCH_PYTHON=%~1"
exit /b 0
