[CmdletBinding()]
param([string]$GameExePath="",[string]$OutputDir="")
$ErrorActionPreference="Stop";$ProgressPreference="SilentlyContinue";[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$scriptRoot=Split-Path -Parent $MyInvocation.MyCommand.Path;$repoRoot=[System.IO.Path]::GetFullPath((Join-Path $scriptRoot "..\.."))
if(-not $OutputDir){$OutputDir=Join-Path $repoRoot "handoff\movement-runtime"}
. (Join-Path $scriptRoot "momentum-runtime-probe-common.ps1")
. (Join-Path $scriptRoot "momentum-runtime-probe-ue4ss.ps1")
. (Join-Path $scriptRoot "momentum-runtime-probe-execute.ps1")
Invoke-MomentumRuntimeProbe $repoRoot $GameExePath $OutputDir
