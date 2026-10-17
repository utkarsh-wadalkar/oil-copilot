<#
.SYNOPSIS
  Fetch, pin, patch and build the nao analytics sidecar image (Task 3N).

.DESCRIPTION
  Reproducible, SHA-pinned setup for the self-hosted nao engine used as the Copilot's analytics
  sidecar. Steps:

    1. ensure vendor/nao is checked out at the exact upstream commit in infra/nao/upstream.sha;
    2. apply the tracked source patch infra/nao/patch/0001-copilot-sidecar.patch (idempotent:
       already-applied patches are detected and skipped);
    3. build the lean image asset-copilot/nao:<short-sha> from infra/nao/Dockerfile.

  The whole vendor/ checkout is git-ignored and is NEVER copied into the app tree by hand.

.PARAMETER SkipFetch
  Do not touch vendor/nao; patch/build the existing checkout as-is.

.PARAMETER SkipBuild
  Stop after fetching + patching (useful in CI).

.EXAMPLE
  pwsh infra/nao/setup-nao.ps1
  pwsh infra/nao/setup-nao.ps1 -SkipFetch -SkipBuild
#>
[CmdletBinding()]
param(
  [string]$Sha,
  [string]$CloneDir,
  [switch]$SkipFetch,
  [switch]$SkipBuild,
  [switch]$ForcePatch
)

$ErrorActionPreference = 'Stop'

$InfraDir = $PSScriptRoot
$RepoRoot = (Resolve-Path (Join-Path $InfraDir '..\..')).Path
$UpstreamShaFile = Join-Path $InfraDir 'upstream.sha'
$PatchFile = Join-Path $InfraDir 'patch\0001-copilot-sidecar.patch'
$Dockerfile = Join-Path $InfraDir 'Dockerfile'

if (-not $Sha) { $Sha = (Get-Content $UpstreamShaFile -Raw).Trim() }
if (-not $CloneDir) { $CloneDir = Join-Path $RepoRoot 'vendor\nao' }
$UpstreamUrl = 'https://github.com/getnao/nao.git'

function Invoke-Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
  & git @GitArgs
  if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed (exit $LASTEXITCODE)" }
}

Write-Host "==> nao sidecar setup" -ForegroundColor Cyan
Write-Host "    commit : $Sha"
Write-Host "    clone  : $CloneDir"

if (-not $SkipFetch) {
  if (Test-Path (Join-Path $CloneDir '.git')) {
    Write-Host "==> vendor/nao already present; ensuring it is at the pinned commit"
    Invoke-Git -C $CloneDir fetch --depth 1 origin $Sha
    Invoke-Git -C $CloneDir checkout --detach $Sha
  }
  else {
    Write-Host "==> cloning $UpstreamUrl"
    Invoke-Git clone --filter=blob:none --no-checkout $UpstreamUrl $CloneDir
    Invoke-Git -C $CloneDir fetch --depth 1 origin $Sha
    Invoke-Git -C $CloneDir checkout --detach $Sha
  }
}

# --- patch (idempotent) ------------------------------------------------------
Write-Host "==> applying tracked patch"
& git -C $CloneDir apply --check --reverse $PatchFile 2>$null
$alreadyApplied = ($LASTEXITCODE -eq 0)
if ($alreadyApplied -and -not $ForcePatch) {
  Write-Host "    patch already applied; skipping" -ForegroundColor Yellow
}
else {
  & git -C $CloneDir apply --check $PatchFile
  if ($LASTEXITCODE -ne 0) {
    throw "patch does not apply cleanly to $CloneDir. Regenerate it with patch/regenerate-patch.ps1."
  }
  Invoke-Git -C $CloneDir apply $PatchFile
  Write-Host "    patch applied"
}

if ($SkipBuild) { Write-Host "==> -SkipBuild set; done" -ForegroundColor Green; exit 0 }

# --- build -------------------------------------------------------------------
$ShortSha = $Sha.Substring(0, 8)
$Tag = "asset-copilot/nao:$ShortSha"
Write-Host "==> docker build -t $Tag (context: $RepoRoot)"
& docker build -f $Dockerfile -t $Tag --build-arg "APP_COMMIT=$Sha" $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "docker build failed (exit $LASTEXITCODE)" }

Write-Host "==> built $Tag" -ForegroundColor Green
