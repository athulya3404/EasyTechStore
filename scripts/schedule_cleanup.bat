@echo off
REM ==============================================================================
REM EasyTech Store - Automated Expired Order Cleanup Scheduler (Windows)
REM Suitable for Windows Task Scheduler execution (e.g. every 5 to 10 minutes)
REM ==============================================================================

echo [%date% %time%] Starting EasyTech Store expired order cleanup sweep...

cd /d "%~dp0\.."

python manage.py cleanup_expired_orders --settings=config.settings.local

if %ERRORLEVEL% equ 0 (
    echo [%date% %time%] Successfully completed expired order cleanup.
) else (
    echo [%date% %time%] Error encountered during cleanup sweep (Exit code: %ERRORLEVEL%).
)
