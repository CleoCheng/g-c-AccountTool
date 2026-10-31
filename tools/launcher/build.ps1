# Rebuilds KeyVault.exe from KeyVaultLauncher.cs using the C# compiler bundled with .NET Framework 4.x
# (preinstalled on Windows 10/11, no Visual Studio required).
# Usage (from repo root):  powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$src  = Join-Path $PSScriptRoot "KeyVaultLauncher.cs"
$icon = Join-Path $root "web\icon.ico"
$out  = Join-Path $root "KeyVault.exe"

$csc = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $csc) { throw "csc.exe (.NET Framework 4.x) not found." }

& $csc /nologo /utf8output /codepage:65001 /target:winexe /out:"$out" /win32icon:"$icon" /r:System.Windows.Forms.dll "$src"
if ($LASTEXITCODE -ne 0) { throw "Build failed." }
Write-Host "Built $out"
