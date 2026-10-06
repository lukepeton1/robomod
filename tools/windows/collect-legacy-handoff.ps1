[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$ExtractRoot,

    [string]$UAssetGUIPath = "",

    [string]$ManifestPath = (Join-Path $PSScriptRoot "..\..\Source\manifests\legacy_patch_targets.txt"),

    [string]$OutputDir = (Join-Path $PSScriptRoot "..\..\handoff\legacy-assets"),

    [switch]$SkipJson,

    [switch]$NoZip
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

$ExtractRoot = Resolve-FullPath $ExtractRoot
$ManifestPath = Resolve-FullPath $ManifestPath

$contentRootCandidates = @(
    (Join-Path $ExtractRoot "RoboQuest\Content"),
    $ExtractRoot
)

$contentRoot = $null
foreach ($candidate in $contentRootCandidates) {
    if (Test-Path (Join-Path $candidate "Data\DT_WeaponAffix.uasset")) {
        $contentRoot = [System.IO.Path]::GetFullPath($candidate)
        break
    }
}
if (-not $contentRoot) {
    throw "Could not find RoboQuest legacy Content root under '$ExtractRoot'. Expected Data\DT_WeaponAffix.uasset. Use retoc to-legacy --version UE4_26 first."
}

$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$rawRoot = Join-Path $OutputDir "raw-legacy\RoboQuest\Content"
$jsonRoot = Join-Path $OutputDir "uassetapi-json\RoboQuest\Content"
New-Item -ItemType Directory -Force -Path $rawRoot | Out-Null
if (-not $SkipJson) {
    if (-not $UAssetGUIPath) {
        throw "UAssetGUIPath is required unless -SkipJson is supplied. Use UAssetGUI v1.1.1+ where possible."
    }
    $UAssetGUIPath = Resolve-FullPath $UAssetGUIPath
    New-Item -ItemType Directory -Force -Path $jsonRoot | Out-Null
}

$targets = Get-Content -LiteralPath $ManifestPath |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith("#") }

$missing = New-Object System.Collections.Generic.List[string]
$records = New-Object System.Collections.Generic.List[object]

foreach ($relative in $targets) {
    $relativeWin = $relative.Replace("/", "\")
    $sourceBase = Join-Path $contentRoot $relativeWin
    $destBase = Join-Path $rawRoot $relativeWin

    $uasset = "$sourceBase.uasset"
    if (-not (Test-Path -LiteralPath $uasset)) {
        $missing.Add("$relative.uasset")
        continue
    }

    New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($destBase)) | Out-Null

    $copied = @()
    foreach ($ext in @(".uasset", ".uexp", ".ubulk")) {
        $src = "$sourceBase$ext"
        if (Test-Path -LiteralPath $src) {
            $dst = "$destBase$ext"
            Copy-Item -LiteralPath $src -Destination $dst -Force
            $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash.ToLowerInvariant()
            $copied += [ordered]@{
                extension = $ext
                bytes = (Get-Item -LiteralPath $dst).Length
                sha256 = $hash
            }
        }
    }

    $jsonRel = $null
    if (-not $SkipJson) {
        $jsonPath = (Join-Path $jsonRoot $relativeWin) + ".json"
        New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($jsonPath)) | Out-Null

        Write-Host "UAssetAPI JSON: $relative"
        & $UAssetGUIPath tojson $uasset $jsonPath 4.26
        if ($LASTEXITCODE -ne 0) {
            throw "UAssetGUI tojson failed for '$uasset' with exit code $LASTEXITCODE."
        }
        if (-not (Test-Path -LiteralPath $jsonPath)) {
            throw "UAssetGUI reported success but did not create '$jsonPath'."
        }
        $jsonRel = [System.IO.Path]::GetRelativePath($OutputDir, $jsonPath).Replace("\", "/")
    }

    $records.Add([ordered]@{
        package = $relative
        files = $copied
        uassetapi_json = $jsonRel
    })
}

$metadata = [ordered]@{
    generated_utc = [DateTime]::UtcNow.ToString("o")
    content_root = $contentRoot
    unreal_version = "4.26"
    target_count = $targets.Count
    collected_count = $records.Count
    missing_count = $missing.Count
    missing = $missing
    packages = $records
}
$manifestOut = Join-Path $OutputDir "handoff-manifest.json"
$metadata | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestOut -Encoding UTF8

if ($missing.Count -gt 0) {
    Write-Warning "$($missing.Count) requested packages were not found. See handoff-manifest.json."
    $missing | ForEach-Object { Write-Warning "Missing: $_" }
}

if (-not $NoZip) {
    $zip = "$OutputDir.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zip -CompressionLevel Optimal
    Write-Host ""
    Write-Host "Created handoff ZIP:"
    Write-Host "  $zip"
}

Write-Host ""
Write-Host "Collected $($records.Count) / $($targets.Count) requested packages."
Write-Host "Manifest: $manifestOut"
if ($SkipJson) {
    Write-Host "UAssetAPI JSON export skipped."
} else {
    Write-Host "UAssetAPI JSON exports: $jsonRoot"
}

if ($missing.Count -gt 0) {
    exit 2
}
