@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"

call :log "Starting containers with docker-compose..."
docker compose -f "%PROJECT_DIR%\docker-compose.yml" up -d
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

call :log "Waiting for MonetDB to be ready..."
set "MDB_READY="
for /l %%I in (1,1,30) do (
    docker exec migration_monetdb mclient -u monetdb -d demo -P monetdb -s "SELECT 1;" >nul 2>&1
    if not errorlevel 1 (
        set "MDB_READY=1"
        goto :monetdb_ready
    )
    timeout /t 4 /nobreak >nul
)

:monetdb_ready
if not defined MDB_READY (
    call :log "MonetDB did not respond in time. Check: docker logs migration_monetdb" RED
    exit /b 1
)
call :log "MonetDB ready." GREEN
exit /b 0

:log
set "MSG=%~1"
set "COLOR=%~2"
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format ''HH:mm:ss''"') do set "NOW=%%T"
if not defined COLOR set "COLOR=Cyan"
echo [%NOW%] %MSG%
exit /b 0
