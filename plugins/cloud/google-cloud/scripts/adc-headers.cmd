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
rem Windows version of scripts/adc-headers, the Claude Code headersHelper for
rem the plugin's MCP servers. .mcp.json names the helper without an extension,
rem so CMD runs this file. Prints the HTTP headers for one connection as a JSON
rem object: a fresh Application Default Credentials access token and the quota
rem project (x-goog-user-project): the ADC file's quota_project_id, else
rem gcloud's billing/quota_project, else the gcloud project. Never prints
rem anything but the headers; errors go to stderr.

setlocal
rem Values go into JSON unescaped, so, as in scripts/adc-headers, only characters
rem an OAuth token or a project ID can have (domain-scoped IDs contain ":") are
rem allowed. Each value is checked right after it's read, before it's used; a
rem checked value has no characters cmd treats as syntax.
set "TOKEN_CHARS=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~+/=-"
set "PROJECT_CHARS=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.:_-"

where gcloud >nul 2>nul
if errorlevel 1 (
  >&2 echo gcloud isn't installed or isn't on PATH: install the Google Cloud CLI, then run: gcloud auth application-default login
  exit /b 1
)

set "TOKEN="
for /f "usebackq delims=" %%T in (`gcloud auth application-default print-access-token 2^>nul`) do set "TOKEN=%%T"
if not defined TOKEN (
  >&2 echo Couldn't get a token from "gcloud auth application-default print-access-token". If you haven't signed in, run: gcloud auth application-default login. Otherwise, run that command yourself to see the error.
  exit /b 1
)
call :keep_if_allowed TOKEN "%TOKEN_CHARS%"
if not defined TOKEN (
  >&2 echo "gcloud auth application-default print-access-token" printed something that isn't a token. Run it yourself to see why.
  exit /b 1
)

set "CONFIG=%CLOUDSDK_CONFIG%"
if not defined CONFIG set "CONFIG=%APPDATA%\gcloud"
set "ADC=%CONFIG%\application_default_credentials.json"
set "QUOTA="
rem PowerShell parses the JSON, so single-line files and ":" in the value work.
if exist "%ADC%" for /f "usebackq delims=" %%Q in (`powershell -NoProfile -NonInteractive -Command "try { (Get-Content -LiteralPath $env:ADC -Raw | ConvertFrom-Json).quota_project_id } catch {}" 2^>nul`) do set "QUOTA=%%Q"
call :keep_if_allowed QUOTA "%PROJECT_CHARS%"
if not defined QUOTA (
  for /f "usebackq delims=" %%Q in (`gcloud config get-value billing/quota_project 2^>nul`) do set "QUOTA=%%Q"
  call :keep_if_allowed QUOTA "%PROJECT_CHARS%"
)
rem Values gcloud accepts for billing/quota_project that aren't project IDs.
if /i "%QUOTA%"=="CURRENT_PROJECT" set "QUOTA="
if /i "%QUOTA%"=="CURRENT_PROJECT_WITH_FALLBACK" set "QUOTA="
if /i "%QUOTA%"=="LEGACY" set "QUOTA="
if not defined QUOTA (
  for /f "usebackq delims=" %%Q in (`gcloud config get-value project 2^>nul`) do set "QUOTA=%%Q"
  call :keep_if_allowed QUOTA "%PROJECT_CHARS%"
)

if defined QUOTA (
  echo {"Authorization":"Bearer %TOKEN%","x-goog-user-project":"%QUOTA%"}
) else (
  echo {"Authorization":"Bearer %TOKEN%"}
)
exit /b 0

:keep_if_allowed
rem Clears the variable named %1 unless every character of its value is in %2.
rem With delayed expansion, the value is expanded after cmd parses the line, so
rem its characters can't act as syntax. for /f splits on the allowed characters:
rem any token left means a character outside them. The leading "x" keeps a value
rem that starts with ";" (the default eol) from being skipped.
setlocal EnableDelayedExpansion
set "OK=1"
for /f "eol=; delims=%~2" %%X in ("x!%~1!") do set "OK="
endlocal & if not "%OK%"=="1" set "%~1="
exit /b 0
