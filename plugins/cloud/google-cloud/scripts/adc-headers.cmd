@echo off
rem Copyright 2026 Google LLC
rem
rem Licensed under the Apache License, Version 2.0 (the "License");
rem you may not use this file except in compliance with the License.
rem You may obtain a copy of the License at
rem
rem     http://www.apache.org/licenses/LICENSE-2.0
rem
rem Unless required by applicable law or agreed to in writing, software
rem distributed under the License is distributed on an "AS IS" BASIS,
rem WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
rem See the License for the specific language governing permissions and
rem limitations under the License.
rem
rem
rem Windows version of scripts/adc-headers, the headers helper for the plugin's
rem MCP servers (Claude Code's headersHelper, Codex's http_headers_helper).
rem .mcp.json names the helper without an extension, so CMD runs this file.
rem Prints the HTTP headers for one connection as a JSON object: an Application
rem Default Credentials access token and the quota project (x-goog-user-project):
rem the ADC file's quota_project_id, else gcloud's billing/quota_project, else
rem the gcloud project. Never prints anything but the headers; errors go to
rem stderr. It works as scripts/adc-headers does, which explains each step: it
rem gets one token at a time, and shares it with the helpers after it.

setlocal
rem As in scripts/adc-headers: gcloud's usage reporting writes the device
rem certificate file from a detached process, outside the lock.
set "CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=true"

where gcloud >nul 2>nul
if errorlevel 1 (
  >&2 echo gcloud isn't installed or isn't on PATH: install the Google Cloud CLI, then run: gcloud auth application-default login
  exit /b 1
)

rem The rest is PowerShell, after the marker below. It runs as a command: the
rem default execution policy would block a .ps1 file. Clients start this file
rem by the extensionless name, where %~f0 is scripts\adc-headers (the bash
rem script), so the path is built from the folder and name.
set "ADC_HEADERS_FILE=%~dpn0.cmd"
powershell -NoProfile -NonInteractive -Command "try { $s = [IO.File]::ReadAllText($env:ADC_HEADERS_FILE); $b = [ScriptBlock]::Create($s.Substring($s.IndexOf('#' + 'POWERSHELL'))) } catch { [Console]::Error.WriteLine('adc-headers.cmd couldn''t load its PowerShell part: ' + $_); exit 1 }; & $b; exit $LASTEXITCODE"
exit /b %errorlevel%

#POWERSHELL
$config = if ($env:CLOUDSDK_CONFIG) { $env:CLOUDSDK_CONFIG } elseif ($env:APPDATA) { Join-Path $env:APPDATA 'gcloud' } else { "$(if ($env:SystemDrive) { $env:SystemDrive } else { 'C:' })\gcloud" }
$haveConfig = Test-Path -LiteralPath $config -PathType Container
# Tokens are shared only in a folder of the user's own: not the system-drive
# fallback, where other users can read folders.
$canShare = $haveConfig -and ($env:CLOUDSDK_CONFIG -or $env:APPDATA)
$adc = Join-Path $config 'application_default_credentials.json'
# Values go into JSON unescaped, so only characters an OAuth token or a project
# ID can have (domain-scoped IDs contain ":") are allowed.
# \A and \z: in .NET, $ also matches before a trailing newline. Matched with
# -cmatch: -match ignores case by the current culture, and in Turkish an
# uppercase I then doesn't match [A-Za-z].
$tokenPattern = '\A[A-Za-z0-9._~+/=-]+\z'
$projectPattern = '\A[A-Za-z0-9.:_-]+\z'

function Write-Headers($token, $quota) {
  if ($quota) {
    [Console]::Out.WriteLine('{"Authorization":"Bearer ' + $token + '","x-goog-user-project":"' + $quota + '"}')
  } else {
    [Console]::Out.WriteLine('{"Authorization":"Bearer ' + $token + '"}')
  }
}

# Token sharing: the token, its expiry, the sign-in and settings it came from,
# and its quota project, in gcloud's folder (under %APPDATA%, only the user's).
$shared = Join-Path $config 'adc-headers.token'
function Get-SignInId {
  $name = $env:CLOUDSDK_ACTIVE_CONFIG_NAME
  if (-not $name) {
    $name = try { ([IO.File]::ReadAllText((Join-Path $config 'active_config'))).Trim() } catch { '' }
  }
  if (-not $name) { $name = 'default' }
  $parts = @(Get-ChildItem Env: | Where-Object { $_.Name -match '^(GOOGLE_APPLICATION_CREDENTIALS|CLOUDSDK_(ACTIVE_CONFIG_NAME|AUTH_|BILLING_|CORE_PROJECT))' } | Sort-Object Name | ForEach-Object { $_.Name + '=' + $_.Value })
  foreach ($file in @($adc, $env:GOOGLE_APPLICATION_CREDENTIALS, (Join-Path $config "configurations\config_$name"))) {
    if ($file -and (Test-Path -LiteralPath $file -PathType Leaf)) { try { $parts += [IO.File]::ReadAllText($file) } catch {} }
  }
  $hash = [Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($parts -join "`n"))
  [BitConverter]::ToString($hash) -replace '-', ''
}
$id = Get-SignInId
function Get-Now { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }
# Writes the headers from the shared file and returns $true, if it's usable.
function Use-Shared {
  if (-not $canShare) { return $false }
  # As in scripts/adc-headers: only for 2 minutes, so a client that runs the
  # helper again after a server rejected its token gets a new one.
  try {
    if ((Get-Item -LiteralPath $shared -ErrorAction Stop).LastWriteTimeUtc -lt [DateTime]::UtcNow.AddSeconds(-120)) { return $false }
    $lines = [IO.File]::ReadAllLines($shared)
  } catch { return $false }
  if ($lines.Count -lt 3) { return $false }
  $sharedQuota = if ($lines.Count -ge 4) { $lines[3] } else { '' }
  if ($lines[0] -notmatch '^\d+$' -or $lines[1] -ne $id -or ([long]$lines[0] - (Get-Now)) -le 300) { return $false }
  if ($lines[2] -cnotmatch $tokenPattern -or ($sharedQuota -and $sharedQuota -cnotmatch $projectPattern)) { return $false }
  Write-Headers $lines[2] $sharedQuota
  return $true
}

if (Use-Shared) { exit 0 }
# One token call at a time: a named mutex shared by every client, which Windows
# releases if the helper is killed. While waiting, a helper uses a token the
# holder has just shared. Clients stop a helper after about 9 s, so it waits at
# most 8 s, then gets the token without the mutex.
$mutex = New-Object System.Threading.Mutex($false, 'Local\google-cloud-adc-headers')
$owned = $false
$wait = if ($env:ADC_HEADERS_LOCK_WAIT -match '^\d+$') { [int]$env:ADC_HEADERS_LOCK_WAIT * 1000 } else { 8000 }
$until = [DateTime]::UtcNow.AddMilliseconds($wait)
while (-not $owned -and [DateTime]::UtcNow -lt $until) {
  try { $owned = $mutex.WaitOne(100) } catch [System.Threading.AbandonedMutexException] { $owned = $true }
  if (-not $owned -and (Use-Shared)) { exit 0 }
}
# Gets a token from gcloud, prints the headers and shares them; returns the
# exit code.
function Get-Headers {
  # gcloud.cmd: PowerShell would run gcloud.ps1, which the default execution
  # policy blocks.
  $got = @(gcloud.cmd auth application-default print-access-token '--format=value(token,expiry)' 2>$null) -join "`n"
  # As scripts/adc-headers: output from a failed call isn't a token.
  if ($LASTEXITCODE -ne 0) { $got = '' }
  $parts = @($got.Trim() -split '\s+', 2)
  $token = $parts[0]
  $expiry = if ($parts.Count -gt 1) { $parts[1] } else { '' }
  if (-not $token) {
    [Console]::Error.WriteLine('Couldn''t get a token from "gcloud auth application-default print-access-token". If you haven''t signed in, or your sign-in has expired, run: gcloud auth application-default login, then reconnect this server or restart your agent. Otherwise, run that command yourself to see the error.')
    return 1
  }
  # The token, then its expiry if gcloud knows it. As in scripts/adc-headers,
  # an expiry in a form this helper doesn't know only stops sharing.
  if ($expiry -and $expiry -notlike 'datetime=*') {
    $got = @(gcloud.cmd auth application-default print-access-token 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) { $got = '' }
    $token = $got.Trim()
    $expiry = ''
  }
  if ($token -cnotmatch $tokenPattern) {
    [Console]::Error.WriteLine('"gcloud auth application-default print-access-token" printed something that isn''t a token. Run it yourself to see why.')
    return 1
  }
  # PowerShell parses the JSON, so single-line files and ":" in the value work.
  $quota = try { "$(([IO.File]::ReadAllText($adc) | ConvertFrom-Json).quota_project_id)" } catch { '' }
  if ($quota -cnotmatch $projectPattern) { $quota = '' }
  if (-not $quota) {
    # Both settings in one gcloud call, tab-separated, as in scripts/adc-headers.
    $settings = (@(gcloud.cmd config list '--format=value(billing.quota_project,core.project)' 2>$null) -join "`n") -split "`t"
    $quota = $settings[0].Trim()
    # Values gcloud accepts for billing/quota_project that aren't project IDs.
    if ($quota -in 'CURRENT_PROJECT', 'CURRENT_PROJECT_WITH_FALLBACK', 'LEGACY' -or $quota -cnotmatch $projectPattern) { $quota = '' }
    if (-not $quota -and $settings.Count -gt 1) { $quota = $settings[1].Trim() }
    if ($quota -cnotmatch $projectPattern) { $quota = '' }
  }
  # gcloud prints the expiry (UTC) as datetime=...;day=23;...;year=2026.
  $f = @{}
  foreach ($pair in $expiry -split ';') { $k, $v = $pair -split '=', 2; $f[$k] = $v }
  # Shared only with an expiry, readable by the current user alone (as
  # scripts/adc-headers does with umask 077).
  if ($canShare -and $expiry) {
    $temp = "$shared.$PID"
    try {
      $expires = [DateTimeOffset]::new([DateTime]::new([int]$f.year, [int]$f.month, [int]$f.day, [int]$f.hour, [int]$f.minute, [int]$f.second, 0, [DateTimeKind]::Utc)).ToUnixTimeSeconds()
      [IO.File]::WriteAllText($temp, '')
      $acl = New-Object System.Security.AccessControl.FileSecurity
      $acl.SetAccessRuleProtection($true, $false)
      $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule([System.Security.Principal.WindowsIdentity]::GetCurrent().User, 'FullControl', 'Allow')))
      [IO.File]::SetAccessControl($temp, $acl)
      [IO.File]::WriteAllText($temp, "$expires`n$id`n$token`n$quota`n")
      Move-Item -LiteralPath $temp -Destination $shared -Force -ErrorAction Stop
    } catch { Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue }
  }
  Write-Headers $token $quota
  return 0
}

$code = 0
try {
  # Shared before the mutex is released, so waiters find it.
  if (-not ($owned -and (Use-Shared))) { $code = Get-Headers }
} finally {
  if ($owned) { $mutex.ReleaseMutex() }
}
exit $code
