<#
.SYNOPSIS
    Packages EasyTechStore into a clean ZIP file for AWS deployment.
.DESCRIPTION
    Excludes local environments (.envs/.local), virtual environments (.venv),
    caches (__pycache__, .pytest_cache), and unneeded files.
#>

$DestinationZip = "d:\EasyTechStore_AWS.zip"

Write-Host "Creating clean deployment package: $DestinationZip ..." -ForegroundColor Cyan

tar.exe -a -c -f $DestinationZip `
    --exclude=".venv" `
    --exclude=".git" `
    --exclude="__pycache__" `
    --exclude="*.pyc" `
    --exclude=".pytest_cache" `
    --exclude="staticfiles" `
    --exclude=".envs/.local" `
    --exclude=".env" `
    *

if (Test-Path $DestinationZip) {
    $sizeMB = [math]::Round((Get-Item $DestinationZip).Length / 1MB, 2)
    Write-Host "SUCCESS! Deployment package created: $DestinationZip ($sizeMB MB)" -ForegroundColor Green
} else {
    Write-Error "Failed to create deployment package."
}
