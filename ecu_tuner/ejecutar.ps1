# Gira en la carpeta del repo por defecto
param([string]$RepoRoot = "$PSScriptRoot")

Set-Location -Path $RepoRoot

$venvScript = ".\venv\Scripts\Activate.ps1"
if (-Not (Test-Path $venvScript)) {
    Write-Host "Creando entorno virtual..."
    python -m venv .\venv
}

Write-Host "Activando entorno..."
& $venvScript

Write-Host "Instalando dependencias..."
pip install -r requirements.txt

# Encoding y salida en UTF-8
chcp 65001
$Env:PYTHONIOENCODING = "utf-8"

Write-Host "Ejecutando ECU Tuner..."
py main.py

Read-Host -Prompt "Presione Enter para salir"
