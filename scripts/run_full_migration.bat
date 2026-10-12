@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"

set "SKIP_IMPORT="
set "WORKERS=1"
set "BATCH_SIZE=10000"
set "CONFIG=postgres_config.json"
set "DUMP_FILE=postgres_export_20250220.sql"

:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--skip-import" (
    set "SKIP_IMPORT=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--workers" (
    set "WORKERS=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--batch-size" (
    set "BATCH_SIZE=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--config" (
    set "CONFIG=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--dump-file" (
    set "DUMP_FILE=%~2"
    shift
    shift
    goto :parse_args
)
if not defined NONFLAG_ARG set "NONFLAG_ARG=%~1"
shift
goto :parse_args

:args_done
if defined NONFLAG_ARG (
    set "DUMP_FILE=%NONFLAG_ARG%"
)

call :log "=== 1. STARTING AND CHECKING DATABASES ===" MAGENTA
call "%SCRIPT_DIR%start_databases.bat"
if errorlevel 1 exit /b %errorlevel%

if not defined SKIP_IMPORT (
    call :log "=== 2. IMPORTING DUMP INTO POSTGRES ===" MAGENTA
    call "%SCRIPT_DIR%import_dump.bat" "%DUMP_FILE%"
    if errorlevel 1 exit /b %errorlevel%
) else (
    call :log "=== 2. DUMP IMPORT SKIPPED (--skip-import) ===" YELLOW
)

call :log "=== 3. CONFIGURING SCHEMA IN MONETDB ===" MAGENTA
set "CONFIG_PATH=%PROJECT_DIR%\config\%CONFIG%"
if not exist "%CONFIG_PATH%" set "CONFIG_PATH=%PROJECT_DIR%\%CONFIG%"
if not exist "%CONFIG_PATH%" (
    call :log "Configuration file not found at: %PROJECT_DIR%\config\%CONFIG% or %PROJECT_DIR%\%CONFIG%" RED
    exit /b 1
)

for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "$cfg = Get-Content -Raw -LiteralPath $env:CONFIG_PATH | ConvertFrom-Json; $cfg.target.schema"`) do set "TARGET_SCHEMA=%%S"
if not defined TARGET_SCHEMA (
    call :log "Could not read target.schema from: %CONFIG_PATH%" RED
    exit /b 1
)

call :log "Creating schema '%TARGET_SCHEMA%' in MonetDB if it does not already exist..."
docker exec migration_monetdb mclient -u monetdb -d demo --password=monetdb -s "CREATE SCHEMA IF NOT EXISTS ""%TARGET_SCHEMA%"";"
if errorlevel 1 exit /b %errorlevel%
call :log "Schema ready." GREEN

call :log "=== 4. STARTING MIGRATOR.PY MIGRATION ===" MAGENTA
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format ''yyyyMMdd_HHmmss''"') do set "TS=%%T"
set "LOG_FILE=%PROJECT_DIR%\migration_local_%TS%.log"

set "PYTHON_CMD=python"
if exist "%PROJECT_DIR%\.venv\Scripts\python.exe" set "PYTHON_CMD=%PROJECT_DIR%\.venv\Scripts\python.exe"

"%PYTHON_CMD%" "%PROJECT_DIR%\migrator.py" --source-type postgres --config "%CONFIG_PATH%" --batch-size %BATCH_SIZE% --workers %WORKERS% --log-file "%LOG_FILE%"
if errorlevel 1 (
    call :log "Migration failed. Check the log at: %LOG_FILE%" RED
    exit /b 1
)

call :log "Migration completed successfully. Log saved to: %LOG_FILE%" GREEN
exit /b 0

:log
set "MSG=%~1"
set "COLOR=%~2"
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format ''HH:mm:ss''"') do set "NOW=%%T"
if not defined COLOR set "COLOR=Cyan"
echo [%NOW%] %MSG%
exit /b 0
