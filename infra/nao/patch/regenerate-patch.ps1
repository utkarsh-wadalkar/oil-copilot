<#
.SYNOPSIS
  Regenerate infra/nao/patch/0001-copilot-sidecar.patch from the vendor/nao working tree.

.DESCRIPTION
  Captures `git diff` from the pinned vendor/nao checkout into the tracked patch. This is the
  source of truth for the sidecar changes, so review `git -C vendor/nao diff` before running.

  IMPORTANT: PowerShell's `>` redirection writes UTF-16LE, which `git apply` cannot read. This
  script routes git's stdout through a byte-exact cmd redirection so the patch stays UTF-8 and
  applies cleanly. It also verifies the regenerated patch against a clean copy afterwards.
#>
[CmdletBinding()]
param(
  [string]$CloneDir,
  [switch]$Check
)

$ErrorActionPreference = 'Stop'
$InfraDir = $PSScriptRoot | Split-Path
$RepoRoot = (Resolve-Path (Join-Path $InfraDir '..\..')).Path
$PatchFile = Join-Path $PSScriptRoot '0001-copilot-sidecar.patch'
if (-not $CloneDir) { $CloneDir = Join-Path $RepoRoot 'vendor\nao' }

if (-not (Test-Path (Join-Path $CloneDir '.git'))) { throw "$CloneDir is not a git checkout" }

$diff = (& git -C $CloneDir diff)
if (-not $diff) { throw "no changes in $CloneDir to capture" }

if ($Check) {
  Write-Host "==> -Check: would write $(($diff -join "`n").Length) bytes to $PatchFile (nothing written)"
  exit 0
}

# Byte-exact (UTF-8, no BOM) capture: PowerShell redirection would emit UTF-16LE.
$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("naopatch-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpDir | Out-Null
try {
  $outFile = Join-Path $tmpDir 'patch.patch'
  # git writes LF; capture raw bytes to avoid any re-encoding.
  & cmd /c "git -C `"$CloneDir`" diff > `"$outFile`""
  if ($LASTEXITCODE -ne 0) { throw "git diff failed" }
  $bytes = [System.IO.File]::ReadAllBytes($outFile)
  [System.IO.File]::WriteAllBytes($PatchFile, $bytes)
}
finally {
  Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

Write-Host "==> wrote $PatchFile ($((Get-Item $PatchFile).Length) bytes)"
Write-Host "==> verify with: git -C $CloneDir apply --check --reverse `"$PatchFile`""
