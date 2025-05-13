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
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Stop-VagrantVM } | Out-Null
[System.Console]::TreatControlCAsInput = $true  # Ensure Ctrl+C is caught

# Main script
try {
    # Start VM only if not already running
    $vmStatus = vagrant status --machine-readable | Select-String ',state,' | ForEach-Object {
        ($_ -split ',')[3]
    }
    $startedByScript = $false
    if ($vmStatus -ne "running") {
        vagrant up
        if ($LASTEXITCODE -ne 0) { throw "Vagrant up failed" }
        $startedByScript = $true
    } else {
        Write-Host "`nVagrant VM already running." -ForegroundColor Green
    }

    # Connect via SSH
    Write-Host "`nConnecting to VM..." -ForegroundColor Cyan
    vagrant ssh -- -t 'cd /vagrant; if [ -n "$BASH_VERSION" ]; then exec bash -l; else exec sh; fi'
    # If SSH session ends (e.g., Ctrl+D), halt only if we started it

} catch {
    Write-Host "`nError: $_" -ForegroundColor Red
    $input = Read-Host -Prompt "Press Enter to run 'vagrant up --debug', Space to run 'vagrant reload', or Ctrl+C to exit"
    if ($input -eq "") {
        Write-Host "`nRunning 'vagrant up --debug'..." -ForegroundColor Cyan
        vagrant up --debug
    } elseif ($input -eq " ") {
        Write-Host "`nRunning 'vagrant reload'..." -ForegroundColor Cyan
        vagrant reload
    }
}

# Cleanup on normal exit
# Stop-VagrantVM

Write-Host "`nThis window will close in 10 seconds..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
Stop-Process -Id $PID
