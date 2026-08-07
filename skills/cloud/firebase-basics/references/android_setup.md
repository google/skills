# 🛠️ Firebase Android Setup Guide

________________________________________________________________________________

## 📋 Prerequisites

## Before running these commands, ensure you are authenticated: `npx -y firebase-tools@latest login` (or `npx -y firebase-tools@latest login --no-localhost` on remote servers)

## 0. Create an Android application

if you haven't already created an android application, create one.

## 1. Create a Firebase Project

If you haven't already created a project, create a new cloud project with a
unique ID: `npx -y firebase-tools@latest projects:create <UNIQUE_PROJECT_ID>
--display-name '<DISPLAY_NAME>'` *Example:* `npx -y firebase-tools@latest
projects:create my-cool-app-20260330 --display-name 'MyCoolApp'`

### 2. Register Your Android App

Link your Android app module (package name) to your project. Notice that the
display name is passed as a positional argument at the end: `npx -y
firebase-tools@latest apps:create ANDROID '<APP_DISPLAY_NAME>' --package-name
'<PACKAGE_NAME>' --project <PROJECT_ID>` *Example:* `npx -y
firebase-tools@latest apps:create ANDROID 'MyApplication' --package-name
'com.example.myapplication' --project my-cool-app-20260330`

### 3. Download `google-services.json`

## Fetch the configuration file using the App ID (which is printed in the output of the previous command): `npx -y firebase-tools@latest apps:sdkconfig ANDROID <APP_ID> --project <PROJECT_ID>` *Example output extraction to file:* ` # (Output must be saved as app/google-services.json)`

## ✅ Verification Plan

### Manual Verification

Validate that the project was created and registered successfully: `npx -y
firebase-tools@latest projects:list` `npx -y firebase-tools@latest apps:list
--project <PROJECT_ID>`

________________________________________________________________________________
