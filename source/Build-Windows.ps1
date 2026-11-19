param([string]$InnoCompiler='C:\Program Files\Inno Setup 7\ISCC.exe')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    python build_desktop.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop executable build failed.' }
    $payload=Join-Path $PSScriptRoot 'build\frozen\PikeCountyWC'
    $destination=Join-Path $PSScriptRoot 'build\installer'
    & $InnoCompiler "/DAppSource=$payload" "/DOutputFolder=$destination" (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
} finally {
    Pop-Location
}
