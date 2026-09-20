<#
.SYNOPSIS
    Builds the nx-skill live bridge: the in-NX server DLL and the console client.

.DESCRIPTION
    Compiles the two C# sources in scripts/dotnet_bridge with the C# compiler that
    ships with the .NET Framework (csc.exe 4.x). No SDK, no NuGet restore and no
    build system are involved.

    Outputs
      <package>/nx_runtime/startup/NxLiveBridgeServer.dll        loaded inside NX
      <package>/scripts/dotnet_bridge/bin/NxLiveBridgeClient.exe console client

    The NX managed assemblies (NXOpen.dll and friends) are compile-time references
    only. They are taken from the root passed with -NxRoot, or from the standard NX
    environment variables; this script deliberately never scans the machine for an
    NX installation, and it contains no machine-specific path. It needs no running
    NX session and no NX license.

.PARAMETER NxRoot
    Directory containing NXBIN, used only to locate the compile-time references.
    Overrides the environment.

.PARAMETER ClientOnly
    Rebuild only the console client. Use this when NX is running and has already
    loaded the server DLL, which keeps that DLL locked.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_dotnet_bridge.ps1
#>
[CmdletBinding()]
param(
    [string]$NxRoot,
    [switch]$ClientOnly
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageRoot = Split-Path -Parent $ScriptDir
$NewLine = [Environment]::NewLine

function Resolve-Csc {
    $Candidates = @(
        (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate) {
            return $Candidate
        }
    }

    $Looked = ($Candidates | ForEach-Object { "  " + $_ }) -join $NewLine
    $Message = @"
The C# compiler shipped with the .NET Framework was not found.

Looked for:
$Looked

Install .NET Framework 4.x (present on every supported Windows version) or
enable its optional feature, then run this script again.
"@
    throw $Message
}

function Resolve-NxManagedDir {
    param([string]$Requested)

    $Candidates = New-Object System.Collections.Generic.List[string]
    if ($Requested) {
        $Candidates.Add($Requested)
    }
    foreach ($Name in @("NX_SKILL_NX_ROOT", "NX_SKILL_ROOT", "NX2512_ROOT", "DC2512_ROOT", "UGII_BASE_DIR")) {
        $Value = [Environment]::GetEnvironmentVariable($Name)
        if ($Value) {
            $Candidates.Add($Value)
        }
    }
    foreach ($Name in @("NX_SKILL_NX_BIN", "NX_SKILL_BIN", "NX2512_BIN", "DC2512_BIN", "UGII_ROOT_DIR")) {
        $Value = [Environment]::GetEnvironmentVariable($Name)
        if ($Value) {
            $Candidates.Add($Value)
        }
    }

    # A candidate may be the NX root, its NXBIN directory, or the managed
    # directory itself. Every one of them is validated by the same fingerprint.
    $Checked = New-Object System.Collections.Generic.List[string]
    foreach ($Candidate in $Candidates) {
        foreach ($Managed in @(
            (Join-Path $Candidate "NXBIN\managed"),
            (Join-Path $Candidate "managed"),
            $Candidate
        )) {
            $Checked.Add($Managed)
            if (Test-Path -LiteralPath (Join-Path $Managed "NXOpen.dll")) {
                return (Resolve-Path -LiteralPath $Managed).Path
            }
        }
    }

    $Looked = ($Checked | ForEach-Object { "  " + $_ }) -join $NewLine
    $Message = @"
The NX managed assemblies needed to compile the live bridge were not found.

Looked for NXOpen.dll in:
$Looked

Pass -NxRoot <directory containing NXBIN>, or set NX_SKILL_NX_ROOT, to an NX
installation whose NXBIN/managed folder holds NXOpen.dll. The bridge is a .NET
Remoting server that loads inside NX, so it must be compiled against that
installation's managed API. Nothing is searched for automatically.
"@
    throw $Message
}

$ManagedDir = Resolve-NxManagedDir -Requested $NxRoot
$Csc = Resolve-Csc

$ServerSource = Join-Path $ScriptDir "dotnet_bridge\server\NxLiveBridgeServer.cs"
$ClientSource = Join-Path $ScriptDir "dotnet_bridge\client\NxLiveBridgeClient.cs"
$ServerOutDir = Join-Path $PackageRoot "nx_runtime\startup"
$ClientOutDir = Join-Path $ScriptDir "dotnet_bridge\bin"
$ServerDll = Join-Path $ServerOutDir "NxLiveBridgeServer.dll"
$ClientExe = Join-Path $ClientOutDir "NxLiveBridgeClient.exe"

foreach ($Source in @($ServerSource, $ClientSource)) {
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Missing C# source: $Source"
    }
}

New-Item -ItemType Directory -Force -Path $ServerOutDir | Out-Null
New-Item -ItemType Directory -Force -Path $ClientOutDir | Out-Null

# NXOpen.dll and NXOpen.UF.dll are used directly. The other two are referenced
# when the installation ships them, so the script also builds against releases
# that name or ship them differently.
$CommonReferences = New-Object System.Collections.Generic.List[string]
foreach ($Required in @("NXOpen.dll", "NXOpen.UF.dll")) {
    $RequiredPath = Join-Path $ManagedDir $Required
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "Missing required NX managed assembly: $RequiredPath"
    }
    $CommonReferences.Add($RequiredPath)
}
foreach ($Optional in @("NXOpenUI.dll", "NXOpen.Utilities.dll")) {
    $OptionalPath = Join-Path $ManagedDir $Optional
    if (Test-Path -LiteralPath $OptionalPath) {
        $CommonReferences.Add($OptionalPath)
    }
}
$CommonReferences.Add("System.Runtime.Remoting.dll")

$Built = New-Object System.Collections.Generic.List[string]

if (-not $ClientOnly) {
    $ServerArgs = @(
        "/nologo",
        "/target:library",
        "/platform:x64",
        "/out:$ServerDll"
    )
    $ServerArgs += $CommonReferences | ForEach-Object { "/reference:$_" }
    $ServerArgs += $ServerSource

    & $Csc @ServerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to compile NxLiveBridgeServer.dll (csc exit code $LASTEXITCODE). If NX is running and has already loaded the bridge, close NX or rerun with -ClientOnly."
    }
    if (-not (Test-Path -LiteralPath $ServerDll)) {
        throw "csc reported success but $ServerDll was not created."
    }
    $Built.Add($ServerDll)
}

$ClientArgs = @(
    "/nologo",
    "/target:exe",
    "/platform:x64",
    "/out:$ClientExe",
    "/reference:System.Web.Extensions.dll"
)
$ClientArgs += $CommonReferences | ForEach-Object { "/reference:$_" }
$ClientArgs += $ClientSource

& $Csc @ClientArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to compile NxLiveBridgeClient.exe (csc exit code $LASTEXITCODE)."
}
if (-not (Test-Path -LiteralPath $ClientExe)) {
    throw "csc reported success but $ClientExe was not created."
}
$Built.Add($ClientExe)

$Summary = [pscustomobject]@{
    csc = $Csc
    nxManagedDir = $ManagedDir
    clientOnly = [bool]$ClientOnly
    built = @($Built)
    serverDll = if ($ClientOnly) { $null } else { $ServerDll }
    clientExe = $ClientExe
}
$Summary | ConvertTo-Json -Depth 4
