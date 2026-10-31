# Builds app\backend-build, the part of the installer that makes it self-contained:
#   python\   a Python runtime (the "embeddable" build from python.org) with Jarvis' packages installed into it
#   backend\  the jarvis package itself
# The installer copies both next to the app, so an installed Jarvis needs no Python and no project folder.
# Run it with the same Python version that is installed on this PC (it downloads the matching runtime):
#   powershell -ExecutionPolicy Bypass -File scripts\prepare-backend.ps1
# With -CodeOnly it only refreshes the jarvis code in an existing build, which takes a second.
param([switch]$CodeOnly)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Split-Path -Parent $here
$project = Split-Path -Parent $app
$out = Join-Path $app "backend-build"

$version = (python -c "import sys, struct; assert struct.calcsize('P') == 8, '64-bit Python is needed'; print('%d.%d.%d' % sys.version_info[:3])").Trim()
Write-Host "Python on this PC: $version"

$haveRuntime = Test-Path "$out\python\Lib\site-packages"
if ($CodeOnly -and -not $haveRuntime) { throw "There is no build to refresh yet. Run this without -CodeOnly first." }
if ($CodeOnly) {
    if (Test-Path "$out\backend") { Remove-Item "$out\backend" -Recurse -Force }
    New-Item -ItemType Directory -Force -Path "$out\backend" | Out-Null
} else {
    if (Test-Path $out) { Remove-Item $out -Recurse -Force }
    New-Item -ItemType Directory -Force -Path "$out\python", "$out\backend" | Out-Null
}

if (-not $CodeOnly) {
    # 1. The runtime
    $zip = Join-Path $env:TEMP "python-$version-embed-amd64.zip"
    if (-not (Test-Path $zip)) {
        Write-Host "Downloading the Python $version runtime..."
        Invoke-WebRequest "https://www.python.org/ftp/python/$version/python-$version-embed-amd64.zip" -OutFile $zip
    }
    Expand-Archive $zip -DestinationPath "$out\python" -Force
    $pth = Get-ChildItem "$out\python" -Filter "python*._pth" | Select-Object -First 1
    # Paths are relative to this file: the packages, and the backend folder that sits next to the python folder
    Set-Content -Path $pth.FullName -Encoding ascii -Value @("python$($version.Split('.')[0])$($version.Split('.')[1]).zip", ".", "Lib\site-packages", "..\backend", "import site")

    # 2. The packages, installed into the runtime's own folder
    Write-Host "Installing the packages (this takes a few minutes)..."
    python -m pip install -r "$project\requirements.txt" --target "$out\python\Lib\site-packages" --no-warn-script-location --disable-pip-version-check --quiet
    if ($LASTEXITCODE -ne 0) { throw "pip failed" }
}

# 3. Jarvis itself, without caches or the saved conversation
robocopy "$project\jarvis" "$out\backend\jarvis" /E /XD __pycache__ conversations /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed" }

# 4. Tidy up, and the licence the installer shows
# Compile everything ahead of time. Without this Python spends the first 20 seconds of the first launch compiling
# thousands of files, and does it again on every launch if the app is installed somewhere it can't save the results.
# "unchecked-hash" files are used as they are, whatever date the installer gives the sources.
Get-ChildItem $out -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Host "Compiling..."
& "$out\python\python.exe" -m compileall -q --invalidation-mode unchecked-hash "$out\python\Lib\site-packages" "$out\backend\jarvis" | Out-Null
Copy-Item "$project\LICENSE" "$out\license.txt"

$size = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Done: {0:N0} MB in {1}" -f $size, $out)
