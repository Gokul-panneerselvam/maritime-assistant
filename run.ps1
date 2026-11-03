# Maritime Operations Assistant — Single-Command Launcher for PowerShell
param (
    [int]$ApiPort = 8080,
    [int]$McpPort = 8000,
    [int]$UiPort = 5173,
    [switch]$NoFrontend = $false,
    [switch]$NoMcp = $false
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Prefer local .venv Python
$pythonExe = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$startScript = Join-Path $scriptDir "start.py"
$cmdArgs = @($startScript, "--port-api", $ApiPort, "--port-mcp", $McpPort, "--port-ui", $UiPort)

if ($NoFrontend) { $cmdArgs += "--no-frontend" }
if ($NoMcp) { $cmdArgs += "--no-mcp" }

Write-Host "Starting Maritime Operations Assistant..." -ForegroundColor Cyan
& $pythonExe $cmdArgs

