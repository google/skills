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
rem Windows version of setup: connects the plugin's two MCP servers in Codex.
rem Sends config.json, with ${PLUGIN_ROOT} replaced by the newest installed
rem version's folder, to Codex's configuration API (codex app-server,
rem config/batchWrite); if that fails, prints the same settings as config.toml
rem lines for the user to add by hand.
rem
rem PowerShell runs the lines after the marker below as a command: the default
rem execution policy blocks .ps1 files, not commands. It starts codex through
rem cmd for the same reason, since npm installs codex as both codex.cmd and
rem codex.ps1.

setlocal
set "CODEX_SETUP_FILE=%~f0"
powershell -NoProfile -NonInteractive -Command "$s = [IO.File]::ReadAllText($env:CODEX_SETUP_FILE); & ([ScriptBlock]::Create($s.Substring($s.IndexOf('#' + 'POWERSHELL')))); exit $LASTEXITCODE"
exit /b %errorlevel%

#POWERSHELL
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$timeout = if ($env:CODEX_SETUP_TIMEOUT) { [int]$env:CODEX_SETUP_TIMEOUT } else { 30 }
$codexConfig = Join-Path $codexHome 'config.toml'
$config = $null
$pluginRoot = $null
$showManual = $false

# A string as TOML writes it. JSON's escapes for " \ and control characters
# are valid in TOML too; ConvertTo-Json also escapes some others as \uXXXX,
# which TOML takes as well.
function ConvertTo-TomlString($s) {
  $json = ConvertTo-Json -InputObject ([string]$s) -Compress
  # PowerShell 5 writes ' & < > as \u0027 and so on; TOML needs no escape for
  # them, and paths read better without. Not after an odd number of \.
  [regex]::Replace($json, '(?<!\\)((?:\\\\)*)\\u00(27|26|3c|3e)', { param($m) $m.Groups[1].Value + [char][Convert]::ToInt32($m.Groups[2].Value, 16) })
}
function ConvertTo-TomlKey($k) { if ($k -match '^[A-Za-z0-9_-]+$') { $k } else { ConvertTo-TomlString $k } }
function ConvertTo-TomlValue($v) {
  if ($v -is [string]) { return ConvertTo-TomlString $v }
  if ($v -is [bool]) { return $(if ($v) { 'true' } else { 'false' }) }
  if ($v -is [array]) {
    return '[' + (($v | ForEach-Object {
      if ($_ -is [Management.Automation.PSCustomObject]) { throw "arrays of objects can't be written here" }
      ConvertTo-TomlValue $_ }) -join ', ') + ']'
  }
  if ($null -eq $v) { throw "can't write null as a value" }
  if ($v -is [ValueType]) { return ([IFormattable]$v).ToString($null, [Globalization.CultureInfo]::InvariantCulture) }
  throw "can't write $($v.GetType().Name) as a value"
}
# config.json's settings as config.toml lines, with ${PLUGIN_ROOT} filled in:
# top-level settings first, then one [table] per section.
function ConvertTo-Toml {
  $tables = [ordered]@{ '' = New-Object Collections.Generic.List[string] }
  function Add-Object($table, $obj) {
    if (-not $tables.Contains($table)) { $tables[$table] = New-Object Collections.Generic.List[string] }
    foreach ($prop in $obj.PSObject.Properties) {
      $key = ConvertTo-TomlKey $prop.Name
      $sub = if ($table) { "$table.$key" } else { $key }
      if ($prop.Value -is [Management.Automation.PSCustomObject]) { Add-Object $sub $prop.Value }
      else { $tables[$table].Add("$key = $(ConvertTo-TomlValue $prop.Value)") }
    }
  }
  $text = [IO.File]::ReadAllText($config).Replace('${PLUGIN_ROOT}', $pluginRoot)
  # Not piped: PowerShell 5 would pass the whole array as one item.
  $edits = ConvertFrom-Json -InputObject $text
  foreach ($edit in $edits) {
    if (-not $edit.keyPath -or -not $edit.PSObject.Properties['value']) { throw 'each edit needs a keyPath and a value' }
    $parts = @($edit.keyPath -split '\.' | ForEach-Object { ConvertTo-TomlKey $_ })
    $table = if ($parts.Count -gt 1) { $parts[0..($parts.Count - 2)] -join '.' } else { '' }
    $key = $parts[-1]
    $sub = if ($table) { "$table.$key" } else { $key }
    if ($edit.value -is [Management.Automation.PSCustomObject]) { Add-Object $sub $edit.value }
    else {
      if (-not $tables.Contains($table)) { $tables[$table] = New-Object Collections.Generic.List[string] }
      $tables[$table].Add("$key = $(ConvertTo-TomlValue $edit.value)")
    }
  }
  $out = New-Object Collections.Generic.List[string]
  foreach ($line in $tables['']) { $out.Add($line) }
  foreach ($name in @($tables.Keys)) {
    if ($name -eq '') { continue }
    $out.Add(''); $out.Add("[$name]"); foreach ($line in $tables[$name]) { $out.Add($line) }
  }
  $out -join "`n"
}

# Says the update failed ($why), and how to retry or add the settings by hand.
function Fail($why) {
  $e = [Console]::Error
  $e.WriteLine("Codex config update failed: $why")
  $e.WriteLine()
  $e.WriteLine('To retry, run this command again.')
  $toml = $null
  if ($showManual -and $config -and (Test-Path -LiteralPath $config)) {
    try { $toml = ConvertTo-Toml } catch { $e.WriteLine("config.json: $($_.Exception.Message)") }
  }
  if ($toml) {
    $e.WriteLine("Or add the settings to $codexConfig yourself:")
    $e.WriteLine('  1. Delete any of the sections below that are already there.')
    $e.WriteLine('  2. Put the lines above the first [section] at the top, before any')
    $e.WriteLine('     [section], and the rest at the end:')
    $e.WriteLine()
    $e.WriteLine($toml)
    $e.WriteLine()
    $e.WriteLine('  3. Restart Codex.')
  }
  exit 1
}

# Compares version folders by the numbers between dots: 2.10.0 is newer than
# 2.9.0.
function Get-VersionKey($name) {
  ($name -split '\.' | ForEach-Object { if ($_ -match '^\d+') { '{0:D10}' -f [long]$Matches[0] } else { '0000000000' } }) -join '.'
}
$helper = Get-ChildItem (Join-Path $codexHome 'plugins\cache\*\google-cloud\*\scripts\adc-headers.cmd') -ErrorAction SilentlyContinue |
  Sort-Object { Get-VersionKey $_.Directory.Parent.Name } | Select-Object -Last 1
if (-not $helper) {
  [Console]::Error.WriteLine("The google-cloud plugin isn't installed in Codex ($codexHome).")
  [Console]::Error.WriteLine('Install it first: codex plugin add google-cloud@google-plugins')
  exit 1
}
$version = $helper.Directory.Parent.Name
$setupDir = Join-Path $helper.Directory.Parent.FullName 'com.google.codex-config'
$config = Join-Path $setupDir 'config.json'
# Forward slashes need no escaping in JSON. Codex runs adc-headers.cmd for the
# extensionless name, as Claude Code does.
$pluginRoot = $helper.Directory.Parent.FullName -replace '\\', '/'
# Codex runs the helper as "<path>" through cmd, where % in a path expands.
if ($pluginRoot.Contains('%')) {
  Fail "the plugin's folder contains %, so Codex can't run its sign-in helper: $pluginRoot`nSet CODEX_HOME to a folder without it, install the plugin there, and run this again."
}

$showManual = $true

$null = & where.exe codex 2>$null
if ($LASTEXITCODE -ne 0) { Fail "codex isn't installed or isn't on PATH." }
if (-not (Test-Path -LiteralPath $config)) {
  Fail "$config is missing. Reinstall the plugin: codex plugin add google-cloud@google-plugins"
}
# JSON strings can't contain line breaks, so removing them keeps the JSON valid
# and puts the request on one line, as codex app-server expects.
$edits = ([IO.File]::ReadAllText($config) -replace '[\r\n]', '').Replace('${PLUGIN_ROOT}', $pluginRoot)
try { $null = $edits | ConvertFrom-Json } catch { Fail "$config isn't valid JSON: $($_.Exception.Message)" }
$request = '{"id":2,"method":"config/batchWrite","params":{"edits":' + $edits + '}}'

$psi = New-Object Diagnostics.ProcessStartInfo 'cmd.exe', '/d /c codex app-server --stdio'
$psi.UseShellExecute = $false; $psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
# Codex reads and writes UTF-8, whatever the console's code page; a path with
# accented letters would otherwise reach it garbled.
$utf8 = New-Object Text.UTF8Encoding $false
$psi.StandardOutputEncoding = $utf8; $psi.StandardErrorEncoding = $utf8
# The config goes where the plugin was found.
$psi.EnvironmentVariables['CODEX_HOME'] = $codexHome
try { $p = [Diagnostics.Process]::Start($psi) } catch { Fail "couldn't start codex: $($_.Exception.Message)" }
# PowerShell 5 can't set the input encoding, so write UTF-8 bytes directly.
$stdin = New-Object IO.StreamWriter($p.StandardInput.BaseStream, $utf8)
$stdin.AutoFlush = $true
$stderr = $p.StandardError.ReadToEndAsync()
$deadline = [DateTime]::Now.AddSeconds($timeout)
$script:timedOut = $false
# Codex's reply to request $id (a parsed JSON-RPC response), or $null if none
# comes in time or Codex exits. Lines that aren't JSON, and requests and
# notifications Codex sends itself (they have a "method"), are skipped.
function Read-Reply($id) {
  while ($true) {
    $left = [int]($deadline - [DateTime]::Now).TotalMilliseconds
    if ($left -le 0) { $script:timedOut = $true; return $null }
    $read = $p.StandardOutput.ReadLineAsync()
    if (-not $read.Wait($left)) { $script:timedOut = $true; return $null }
    if ($null -eq $read.Result) { return $null } # Codex closed its output.
    try { $msg = ConvertFrom-Json -InputObject $read.Result } catch { continue }
    if ($null -eq $msg -or $msg.PSObject.Properties['method']) { continue }
    if ($msg.PSObject.Properties['id'] -and "$($msg.id)" -eq "$id") { return $msg }
  }
}
# In PowerShell 7 a write to a codex that has exited throws (5.1 ignores it);
# the checks below report why codex stopped.
$init = $null
try {
  $stdin.WriteLine('{"id":1,"method":"initialize","params":{"clientInfo":{"name":"google-cloud-setup","version":"1.0"}}}')
  $init = Read-Reply 1
} catch {}
$reply = $null
if ($init) {
  try {
    $stdin.WriteLine('{"method":"initialized"}')
    $stdin.WriteLine($request)
    $reply = Read-Reply 2
  } catch {}
}
try { $stdin.Close() } catch {}
$exited = $p.WaitForExit(5000)
if (-not $exited) { & taskkill.exe /t /f /pid $p.Id 2>&1 | Out-Null }
if ($reply -and $reply.PSObject.Properties['result'] -and $reply.result.status -eq 'ok') {
  "Codex config updated (google-cloud $version). Restart Codex to use it."
  exit 0
}
if ($reply) { Fail "Codex answered: $(ConvertTo-Json -InputObject $reply -Compress -Depth 10)" }
if (-not $script:timedOut -and $exited) {
  $err = if ($stderr.Wait(1000)) { ($stderr.Result -replace '\s+', ' ').Trim() } else { '' }
  if ($err.Length -gt 300) { $err = $err.Substring(0, 300) }
  if (-not $err) { $err = 'no message' }
  Fail "codex app-server stopped (exit $($p.ExitCode)): $err`nCheck that 'codex app-server --help' works; your Codex may be too old."
}
Fail "Codex didn't answer within $timeout s."
