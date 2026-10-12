@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"

set "DUMP_FILE=postgres_export_20250220.sql"
if not "%~1"=="" set "DUMP_FILE=%~1"

call :log "Ensuring the Postgres container is up..."
docker compose -f "%PROJECT_DIR%\docker-compose.yml" up -d postgres
if errorlevel 1 exit /b %errorlevel%

call :log "Waiting for Postgres 16 to be ready..."
set "PG_READY="
for /l %%I in (1,1,40) do (
    docker exec migration_postgres pg_isready -U postgres -d django_postgres_db >nul 2>&1
    if not errorlevel 1 (
        set "PG_READY=1"
        goto :postgres_ready
    )
    timeout /t 3 /nobreak >nul
)

:postgres_ready
if not defined PG_READY (
    call :log "Postgres did not respond in time. Check: docker logs migration_postgres" RED
    exit /b 1
)
call :log "Postgres ready." GREEN

set "DUMP_PATH=%PROJECT_DIR%\data\%DUMP_FILE%"
if not exist "%DUMP_PATH%" set "DUMP_PATH=%PROJECT_DIR%\%DUMP_FILE%"
if not exist "%DUMP_PATH%" (
    if exist "%DUMP_FILE%" (
        for %%F in ("%DUMP_FILE%") do set "DUMP_PATH=%%~fF"
    ) else (
        call :log "Dump not found: %DUMP_FILE% (checked in data/ and project root)" RED
        exit /b 1
    )
)

for %%F in ("%DUMP_PATH%") do set "DUMP_SIZE_BYTES=%%~zF"
set /a "DUMP_SIZE_MB=(DUMP_SIZE_BYTES + 524288) / 1048576"
call :log "Importing dump (!DUMP_SIZE_MB! MB) into Postgres. This may take a while..."

for %%F in ("%DUMP_PATH%") do set "DUMP_LEAF=%%~nxF"
docker exec migration_postgres psql -U postgres -d django_postgres_db -f "/dump/%DUMP_LEAF%"
if errorlevel 1 (
    call :log "Error during dump import into Postgres." RED
    exit /b 1
)
call :log "Dump imported successfully into Postgres." GREEN
exit /b 0

:log
set "MSG=%~1"
set "COLOR=%~2"
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format ''HH:mm:ss''"') do set "NOW=%%T"
if not defined COLOR set "COLOR=Cyan"
echo [%NOW%] %MSG%
exit /b 0
