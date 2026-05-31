# Register the antigravity-ide protocol handler for the current user
$RegistryPath = "HKCU:\Software\Classes\antigravity-ide"

Write-Host "Creating registry key at $RegistryPath..."
if (-not (Test-Path $RegistryPath)) {
    New-Item -Path $RegistryPath -Force | Out-Null
}
Set-Item -Path $RegistryPath -Value "URL:antigravity-ide Protocol"
Set-ItemProperty -Path $RegistryPath -Name "URL Protocol" -Value ""

$IconPath = "$RegistryPath\DefaultIcon"
if (-not (Test-Path $IconPath)) {
    New-Item -Path $IconPath -Force | Out-Null
}
Set-Item -Path $IconPath -Value '"C:\Users\Usuario\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe",0'

$CommandPath = "$RegistryPath\shell\open\command"
if (-not (Test-Path $CommandPath)) {
    New-Item -Path $CommandPath -Force | Out-Null
}
Set-Item -Path $CommandPath -Value '"C:\Users\Usuario\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe" "%1"'

Write-Host "Protocol registered successfully!"
