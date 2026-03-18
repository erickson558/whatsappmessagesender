param(
    [string]$PythonExe = "python",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ProjectRoot
try {
    $Version = (Get-Content -Raw -Path "VERSION").Trim()
    if (-not $Version) {
        throw "El archivo VERSION esta vacio."
    }

    $VersionFile = Join-Path $ProjectRoot "build_artifacts\\version_info.txt"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $VersionFile) | Out-Null

    Write-Host "Instalando dependencias..."
    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la actualizacion de pip (exit code $LASTEXITCODE)."
    }

    & $PythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la instalacion de dependencias (exit code $LASTEXITCODE)."
    }

    & $PythonExe .\scripts\build_windows_version_file.py --version $Version --output $VersionFile
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo generar el archivo de version para PyInstaller."
    }

    if (Test-Path ".\enviar_whatsapp.exe") {
        Remove-Item ".\enviar_whatsapp.exe" -Force
    }

    $VersionDataArg = "{0};." -f (Join-Path $ProjectRoot "VERSION")

    Write-Host "Compilando enviar_whatsapp.exe v$Version ..."
    $pyiArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "enviar_whatsapp",
        "--distpath", ".",
        "--workpath", "build",
        "--specpath", "build_artifacts",
        "--icon", "enviar_whatsapp.ico",
        "--version-file", $VersionFile,
        "--collect-submodules", "playwright",
        "--collect-data", "tkcalendar",
        "--hidden-import", "playwright.sync_api",
        "--hidden-import", "playwright._impl._errors",
        "--add-data", $VersionDataArg,
        "enviar_whatsapp.py"
    )
    if ($Clean) {
        $pyiArgs = @("-m", "PyInstaller", "--clean") + $pyiArgs[2..($pyiArgs.Length - 1)]
    }

    & $PythonExe @pyiArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo PyInstaller (exit code $LASTEXITCODE)."
    }

    Write-Host "Listo. Ejecutable generado en: .\\enviar_whatsapp.exe"
}
finally {
    Pop-Location
}
