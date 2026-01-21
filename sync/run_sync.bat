@echo off
REM Simple Confluence to Open WebUI Sync Runner (Windows)

echo 🚀 Starting Confluence sync...

REM Handle list-spaces command
if "%1"=="--list-spaces" (
    if "%4"=="" (
        echo Usage: %0 --list-spaces ^<confluence-url^> ^<username^> ^<token^>
        goto :error
    )
    python confluence_sync.py --list-spaces --confluence-url "%2" --confluence-username "%3" --confluence-token "%4"
    goto :eof
)

REM Handle spaces command
if "%1"=="--spaces" (
    if "%7"=="" (
        echo Usage: %0 --spaces "SPACE1,SPACE2" ^<openwebui-url^> ^<api-key^> ^<confluence-url^> ^<username^> ^<token^> [knowledge-base-name]
        goto :error
    )

    set SPACES=%2
    set OPENWEBUI_URL=%3
    set API_KEY=%4
    set CONFLUENCE_URL=%5
    set USERNAME=%6
    set TOKEN=%7
    set KB_NAME=%8

    if "%KB_NAME%"=="" set KB_NAME=Confluence-Multiple

    echo 📋 Configuration:
    echo   Spaces: %SPACES%
    echo   Open WebUI: %OPENWEBUI_URL%
    echo   Knowledge Base: %KB_NAME%
    echo.

    python confluence_sync.py ^
        --spaces "%SPACES%" ^
        --openwebui-url "%OPENWEBUI_URL%" ^
        --api-key "%API_KEY%" ^
        --confluence-url "%CONFLUENCE_URL%" ^
        --confluence-username "%USERNAME%" ^
        --confluence-token "%TOKEN%" ^
        --knowledge-base-name "%KB_NAME%"

    echo ✅ Sync completed!
    goto :eof
)

REM Handle single space sync
if "%~6"=="" (
    echo Usage options:
    echo   List spaces: %0 --list-spaces ^<confluence-url^> ^<username^> ^<token^>
    echo   Sync space:   %0 ^<space-key^> ^<openwebui-url^> ^<api-key^> ^<confluence-url^> ^<username^> ^<token^> [knowledge-base-name] [description] [force-refresh]
    echo   Sync spaces:  %0 --spaces "SPACE1,SPACE2" ^<openwebui-url^> ^<api-key^> ^<confluence-url^> ^<username^> ^<token^> [knowledge-base-name]
    echo.
    echo Examples:
    echo   %0 --list-spaces https://company.atlassian.net user@company.com token123
    echo   %0 MYSPACE http://localhost:3000 my-api-key https://company.atlassian.net user@company.com token123
    echo   %0 --spaces "DOCS,PROJ" http://localhost:3000 my-api-key https://company.atlassian.net user@company.com token123
    goto :error
)

set SPACE_KEY=%1
set OPENWEBUI_URL=%2
set API_KEY=%3
set CONFLUENCE_URL=%4
set USERNAME=%5
set TOKEN=%6
set KB_NAME=%7
set DESCRIPTION=%8
set FORCE_REFRESH=%9

if "%KB_NAME%"=="" set KB_NAME=Confluence-%SPACE_KEY%
if "%DESCRIPTION%"=="" set DESCRIPTION=Synced from Confluence space %SPACE_KEY%
if "%FORCE_REFRESH%"=="" set FORCE_REFRESH=false

echo 📋 Configuration:
echo   Space: %SPACE_KEY%
echo   Open WebUI: %OPENWEBUI_URL%
echo   Knowledge Base: %KB_NAME%
echo   Force Refresh: %FORCE_REFRESH%
echo   Confluence: %CONFLUENCE_URL%
echo.

REM Build command
set CMD=python confluence_sync.py ^
    --space-key "%SPACE_KEY%" ^
    --openwebui-url "%OPENWEBUI_URL%" ^
    --api-key "%API_KEY%" ^
    --confluence-url "%CONFLUENCE_URL%" ^
    --confluence-username "%USERNAME%" ^
    --confluence-token "%TOKEN%" ^
    --knowledge-base-name "%KB_NAME%" ^
    --description "%DESCRIPTION%"

if "%FORCE_REFRESH%"=="true" (
    set CMD=%CMD% --force-refresh
)

REM Run the sync
%CMD%

echo ✅ Sync completed!
goto :eof

:error
exit /b 1