# Builds AavFilter.sys (x64) with the Windows Driver Kit, without a Visual Studio project.
# Usage (Developer PowerShell or CI on windows-2022):  pwsh agent/kernel/windows/build.ps1 [-OutDir out]
# Signing: test-sign for development (bcdedit /set testsigning on; signtool sign /fd sha256 /a ...); production
# needs Microsoft attestation signing via Partner Center with an EV certificate (register B-01).
param([string]$OutDir = "$PSScriptRoot\out")
$ErrorActionPreference = "Stop"
$kits = "${env:ProgramFiles(x86)}\Windows Kits\10"
$ver = Get-ChildItem "$kits\Include" -Directory | Where-Object { Test-Path "$($_.FullName)\km\fltKernel.h" } |
       Sort-Object Name -Descending | Select-Object -First 1
if (-not $ver) { throw "Windows Driver Kit not found (fltKernel.h missing under $kits\Include). Install the WDK." }
$v = $ver.Name
$vs = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * `
      -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$msvc = Get-ChildItem "$vs\VC\Tools\MSVC" -Directory | Sort-Object Name -Descending | Select-Object -First 1
$bin = "$($msvc.FullName)\bin\Hostx64\x64"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$inc = @("$kits\Include\$v\km", "$kits\Include\$v\shared", "$kits\Include\$v\km\crt", "$($msvc.FullName)\include")
$lib = "$kits\Lib\$v\km\x64"
# /wd4324: the WDK's own fltKernel.h pads structures (C4324) and would otherwise fail /WX.
$cflags = @("/nologo", "/c", "/kernel", "/W4", "/WX", "/wd4324", "/O2", "/GS", "/Gy", "/Zi", "/D_AMD64_", "/DAMD64", "/D_WIN64",
            "/DNTDDI_VERSION=0x0A00000C", "/D_WIN32_WINNT=0x0A00", "/DPOOL_NX_OPTIN=1", "/Fo$OutDir\AavFilter.obj",
            "/Fd$OutDir\AavFilter.pdb") + ($inc | ForEach-Object { "/I$_" })
& "$bin\cl.exe" @cflags "$PSScriptRoot\AavFilter.c"
if ($LASTEXITCODE) { throw "compile failed" }
& "$bin\link.exe" /nologo /DRIVER /SUBSYSTEM:NATIVE /ENTRY:DriverEntry /NODEFAULTLIB /RELEASE /DEBUG `
   /INTEGRITYCHECK /OUT:"$OutDir\AavFilter.sys" /PDB:"$OutDir\AavFilter.sys.pdb" "/LIBPATH:$lib" `
   "$OutDir\AavFilter.obj" fltMgr.lib ntoskrnl.lib hal.lib BufferOverflowFastFailK.lib
if ($LASTEXITCODE) { throw "link failed" }
Copy-Item "$PSScriptRoot\AavFilter.inf" $OutDir
Write-Host "built $OutDir\AavFilter.sys (unsigned)"
