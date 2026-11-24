# Build script for Eletrozone NetScan standalone Windows executable
$ErrorActionPreference = "Stop"

Write-Host "Compilando EletrozoneNetScan.exe..." -ForegroundColor Red

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "EletrozoneNetScan" `
    --icon "assets/eletrozone.ico" `
    --add-data "assets/eletrozone_logo.png;assets" `
    --add-data "assets/eletrozone.ico;assets" `
    --exclude-module kivy `
    --exclude-module kivymd `
    --exclude-module matplotlib `
    --exclude-module numpy `
    --exclude-module pandas `
    --exclude-module scipy `
    --exclude-module tkinter `
    main.py

if (Test-Path "dist/EletrozoneNetScan.exe") {
    $info = Get-Item "dist/EletrozoneNetScan.exe"
    Write-Host "Build concluido com sucesso: $($info.FullName) ($([math]::Round($info.Length / 1MB, 2)) MB)" -ForegroundColor Green
} else {
    throw "Executavel nao encontrado apos o build!"
}
