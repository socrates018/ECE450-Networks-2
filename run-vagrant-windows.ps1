# Run as Admin (restart if not elevated)
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`"" -Verb RunAs
    exit
}

# Ensure Vagrant is in PATH for this session
$vagrantInstallDir = "${env:ProgramFiles}\Vagrant\bin"
if (-not ($env:PATH -split ';' | Where-Object { $_ -eq $vagrantInstallDir })) {
    $env:PATH = "$vagrantInstallDir;$env:PATH"
}

# Ensure user/AppData/Local/Temp exists
$tempDir = Join-Path $env:LOCALAPPDATA "Temp"
if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir | Out-Null
}

# Ensure C:\tmp exists
$cTmpDir = "C:\tmp"
if (-not (Test-Path $cTmpDir)) {
    New-Item -ItemType Directory -Path $cTmpDir | Out-Null
}

# Set Vagrant directory (universal for any user)
$vagrantDir = Join-Path $env:USERPROFILE "Documents\mininet-vm"
Set-Location $vagrantDir

# Function to halt VM safely
function Stop-VagrantVM {
    Write-Host "`nShutting down Vagrant VM..." -ForegroundColor Yellow
    vagrant halt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "VM halted successfully." -ForegroundColor Green
    } else {
        Write-Host "Failed to halt VM. Manually run 'vagrant halt'." -ForegroundColor Red
    }
    Start-Sleep -Seconds 2  # Pause to show message
}

# Trap window close/Ctrl+C to trigger shutdown
# Only register shutdown handler if we started the VM
$global:startedByScript = $false
function Register-ShutdownHandler {
    Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { 
        if ($global:startedByScript) { Stop-VagrantVM }
    } | Out-Null
    [System.Console]::TreatControlCAsInput = $true  # Ensure Ctrl+C is caught
}

# Main script
try {
    # Start VM only if not already running
    $vmStatus = vagrant status --machine-readable | Select-String ',state,' | ForEach-Object {
        ($_ -split ',')[3]
    }
    $global:startedByScript = $false
    if ($vmStatus -ne "running") {
        vagrant up
        if ($LASTEXITCODE -ne 0) { throw "Vagrant up failed" }
        $global:startedByScript = $true
        # Register-ShutdownHandler
    } else {
        Write-Host "`nVagrant VM already running." -ForegroundColor Green
    }

    # Connect via SSH in the current PowerShell window and wait for it to close
    Write-Host "`nConnecting to VM..." -ForegroundColor Cyan
    vagrant ssh -- -t 'cd /vagrant; if [ -n "$BASH_VERSION" ]; then exec bash -l; else exec sh; fi'

    # Prompt to halt VM if SSH session ends (e.g., Ctrl+D)
    if ($global:startedByScript) {
        $response = Read-Host "`nDo you want to halt the VM? [Y/n]"
        if ($response -eq "" -or $response -match "^[Yy]") {
            Stop-VagrantVM
        } else {
            Write-Host "VM left running." -ForegroundColor Yellow
        }
    }

    Write-Host "`nDone." -ForegroundColor Yellow

} catch {
    Write-Host "`nError: $_" -ForegroundColor Red
    while ($true) {
        Write-Host "Press Enter to run 'vagrant up --debug', Spacebar to run 'vagrant reload', or Ctrl+D to exit"
        $key = [System.Console]::ReadKey($true)
        if ($key.Key -eq 'Enter') {
            Write-Host "`nRunning 'vagrant up --debug'..." -ForegroundColor Cyan
            vagrant up --debug
        } elseif ($key.Key -eq 'Spacebar') {
            Write-Host "`nRunning 'vagrant reload'..." -ForegroundColor Cyan
            vagrant reload
        }
    }
}

# Cleanup on normal exit
# Stop-VagrantVM
