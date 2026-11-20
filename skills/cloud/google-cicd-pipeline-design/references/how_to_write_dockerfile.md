# Comprehensive Guide to Writing Dockerfiles

This document is a detailed guideline for writing professional-grade Dockerfiles
for Google Cloud Run and Google Kubernetes Engine (GKE).

## Table of Contents

-   [1. Core Principles: Thinking in Layers](#1-core-principles-thinking-in-layers)
    (Lines 16-32)
-   [2. General Best Practices](#2-general-best-practices) (Lines 34-53)
-   [3. Multi-Stage Builds (The Gold Standard)](#3-multi-stage-builds-the-gold-standard)
    (Lines 57-179)
-   [4. Recommended Base Images](#4-recommended-base-images) (Lines 183-304)
-   [5. Summary Checklist](#5-summary-checklist) (Lines 308-327)

## 1. Core Principles: Thinking in Layers

A Docker image is a stack of read-only layers. Each instruction (`RUN`, `COPY`,
`ADD`) creates a new layer.

*   **Optimize the Cache:** Order instructions from **least frequent to most
    frequent change**.
*   *Bad:* Copying all source code, then running `npm install`. (Cache busts on
    every code change).
*   *Good:* Copy `package.json`, run `install`, *then* copy source code.
*   *Install dependencies first:* For all languages, install dependencies before
    copying source code. This leverages Docker's layer caching.

*   **Combine RUN commands:** Use `&&` and line breaks (`\`) to group related
    commands (e.g.,
    `apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*`)
    to keep the layer count and image size down.

## 2. General Best Practices

*   **Sort Multi-line arguments:** When writing RUN commands with multiple
    arguments, sort them alphabetically to improve readability and
    maintainability.
*   **COPY vs ADD:** Always use `COPY`. Use `ADD` only if you need to
    auto-extract a local `.tar` file into the image.
*   **Use `.dockerignore` (and `.gcloudignore`):** Create `.dockerignore` and
    `.gcloudignore` to exclude `node_modules`, `.git`, `.gcp-deploy/`, logs, and
    secret files (`.env*`, `*.pem`, `*.key`, `*credentials*.json`) from being
    sent to the build context. Never bake secrets into `ENV` or `ARG`
    instructions; inject them at runtime via Google Cloud Secret Manager
    (`--set-secrets`).
*   **Run as Non-Root:** By default, containers run as root. For production,
    create a user with a UID above 10,000 to prevent host-escalation attacks.

```dockerfile
RUN groupadd -g 10001 appgroup && useradd -u 10000 -g appgroup appuser
USER appuser
```

--------------------------------------------------------------------------------

## 3. Multi-Stage Builds (The Gold Standard)

Multi-stage builds allow you to use a heavy image (with compilers and build
tools) for the build process and a tiny image (just the runtime) for the final
production container. Always use multi stage builds when possible.

### Why use Multi-Stage?

1.  **Drastic Size Reduction:** Your final image won't contain compilers, header
    files, or build caches.
2.  **Security:** Fewer binaries in the final image mean a smaller attack
    surface.
3.  **Simplicity:** You don't need separate build scripts; the entire CI/CD
    pipeline is documented in one Dockerfile.

### 💡 Example 1: Node.js (Standard Production Pattern)

This pattern separates the `npm install` (with dev dependencies for building)
from the production runtime.

```dockerfile
# --- Stage 1: Build & Test ---
FROM node:22-bookworm AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci  # Clean install including dev dependencies
COPY . .
RUN npm run build

# --- Stage 2: Production Runtime ---
FROM node:22-bookworm-slim AS runtime
WORKDIR /app
# Only copy production dependencies and the built dist folder
COPY --from=builder /app/package*.json ./
RUN npm ci --only=production
COPY --from=builder /app/dist ./dist

ENV PORT=8080
EXPOSE 8080
USER node
CMD ["node", "dist/index.js"]
```

### 💡 Example 2: Go (Compiled to Distroless/Scratch)

For compiled languages like Go, Rust, or C++, the final image can be effectively
"empty" except for your binary.

```dockerfile
# --- Stage 1: Build ---
FROM golang:1.23-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
# Build a statically linked binary
RUN CGO_ENABLED=0 GOOS=linux go build -o /bin/app ./main.go

# --- Stage 2: Runtime ---
# Using Google's "distroless" for maximum security (no shell, no package manager)
FROM gcr.io/distroless/static-debian12
COPY --from=builder /bin/app /app
ENV PORT=8080
EXPOSE 8080
USER 1000:1000
ENTRYPOINT ["/app"]
```

### 💡 Example 3: Python Application (Cloud Run & GKE Ready)

```dockerfile
# --- Stage 1: Builder Stage ---
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# --- Stage 2: Final (Runtime) Stage ---
FROM python:3.12-slim AS final
WORKDIR /app
RUN groupadd -g 10001 appgroup && useradd -u 10000 -g appgroup appuser
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app .

ENV PORT=8080
EXPOSE 8080
USER appuser
CMD ["python", "app.py"]
```

### 💡 Example 4: AI Agent or MCP Server (Python ADK / FastMCP / Uvicorn)

When containerizing an IDE-generated **AI Agent** (`google-adk`, `langchain`,
`langgraph`) or **MCP Server** (`fastmcp`, `mcp`), ensure the server binds to
`0.0.0.0:${PORT:-8080}` and never hardcodes API keys (`GEMINI_API_KEY`,
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) in the `Dockerfile`:

```dockerfile
# --- Stage 1: Builder Stage ---
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# --- Stage 2: Production Runtime ---
FROM python:3.12-slim AS runtime
WORKDIR /app
RUN groupadd -g 10001 appgroup && useradd -u 10000 -g appgroup appuser
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app .

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
EXPOSE 8080
USER appuser

# Bind to 0.0.0.0:$PORT for Cloud Run and GKE health probes
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

--------------------------------------------------------------------------------

## 4. Recommended Base Images

### Generic Base Image suggestions

*   For programming languages use their official base image.
*   Use latest version of the language specific image as base image.
*   Review project config files to identify required runtime version:
    *   When a runtime version is specified, use that version for the base
        image.
    *   If no minimum version is specified, use a recent stable version of the
        runtime.

### Google Cloud Run Specific Base Images

If you are deploying to **Google Cloud Run**, you can leverage advanced features
for security and maintenance.

#### Base Image for Cloud Run Automatic Updates

Google Cloud can automatically patch security vulnerabilities in your base image
if you follow the **"Scratch Pattern"**.

1.  In your Dockerfile, copy your app onto a `FROM scratch` image.
2.  Deploy to Cloud Run using the `--base-image` flag.

**Dockerfile for Cloud Run Automatic Updates:**

```dockerfile
FROM node:24-slim AS builder
WORKDIR /usr/src/app
COPY package*.json ./
RUN npm install --only=production
COPY . .

# Final stage: Start from scratch (Cloud Run will inject the OS/Runtime layers)
FROM scratch
WORKDIR /workspace
# Note: chown 33:33 is a common pattern for the 'www-data' user in Google's stacks
COPY --from=builder --chown=33:33 /usr/src/app/ ./
USER 33:33
CMD [ "node", "index.js" ]
```

#### Recommended Base Images (Stacks)

A base image serves as the starting foundation for container-based development.
You build your application by layering necessary libraries, binaries, and
configuration files on top of this image. Google Cloud's buildpacks publish
these images with various configurations for system packages and languages.

##### Key Guidelines

*   **Hosting**: Base images are hosted in every region where the Artifact
    Registry is available.
*   **Updates**: Security and maintenance updates are released routinely.
    Depending on your environment (e.g., Cloud Run functions) and configuration,
    these updates can be applied automatically or manually.
*   **URI Format**: To use a base image, you reference it using a specific URI
    structure which you can customize based on your location and requirements:
    `REGION-docker.pkg.dev/serverless-runtimes/STACK/runtimes/RUNTIME_ID`

**Customization Steps** You need to replace the specific portions of the URI
with your own values:

*   **REGION**: Replace with your preferred region (e.g., us-central1).
*   **STACK**: Replace with your preferred operating system stack (e.g.,
    google-24).
*   **RUNTIME_ID**: Replace with the specific ID for your language runtime
    (e.g., python313 or nodejs24). Detailed list of runtime ids is below:

Runtime IDs and environment details (mostly Ubuntu 22.04 or 18.04, with some
newer Ubuntu 24.04 options) for the following languages:

| Language  | Runtime     | Generation       | Environment  | Runtime ID |
| :-------- | :---------- | :--------------- | :----------- | :--------- |
| Node.js   | Node.js 24  | 2nd gen          | Ubuntu 24.04 | nodejs24   |
| Node.js   | Node.js 22  | 1st gen, 2nd gen | Ubuntu 22.04 | nodejs22   |
| Node.js   | Node.js 20  | 1st gen, 2nd gen | Ubuntu 22.04 | nodejs20   |
| Node.js   | Node.js 18  | 1st gen, 2nd gen | Ubuntu 22.04 | nodejs18   |
| Node.js   | Node.js 16  | 1st gen, 2nd gen | Ubuntu 18.04 | nodejs16   |
| Node.js   | Node.js 14  | 1st gen, 2nd gen | Ubuntu 18.04 | nodejs14   |
| Node.js   | Node.js 12  | 1st gen, 2nd gen | Ubuntu 18.04 | nodejs12   |
| Node.js   | Node.js 10  | 1st gen, 2nd gen | Ubuntu 18.04 | nodejs10   |
| Node.js   | Node.js 8   | 1st gen, 2nd gen | Ubuntu 18.04 | nodejs8    |
| Node.js   | Node.js 6   | 1st gen, 2nd gen | Ubuntu 18.04 | nodejs6    |
| Python    | Python 3.14 | 2nd gen          | Ubuntu 24.04 | python314  |
| Python    | Python 3.13 | 2nd gen          | Ubuntu 22.04 | python313  |
| Python    | Python 3.12 | 1st gen, 2nd gen | Ubuntu 22.04 | python312  |
| Python    | Python 3.11 | 1st gen, 2nd gen | Ubuntu 22.04 | python311  |
| Python    | Python 3.10 | 1st gen, 2nd gen | Ubuntu 22.04 | python310  |
| Python    | Python 3.9  | 1st gen, 2nd gen | Ubuntu 18.04 | python39   |
| Python    | Python 3.8  | 1st gen, 2nd gen | Ubuntu 18.04 | python38   |
| Python    | Python 3.7  | 1st gen          | Ubuntu 18.04 | python37   |
| Go        | Go 1.25     | 2nd gen          | Ubuntu 22.04 | go125      |
| Go        | Go 1.24     | 2nd gen          | Ubuntu 22.04 | go124      |
| Go        | Go 1.23     | 2nd gen          | Ubuntu 22.04 | go123      |
| Go        | Go 1.22     | 2nd gen          | Ubuntu 22.04 | go122      |
| Go        | Go 1.21     | 1st gen, 2nd gen | Ubuntu 22.04 | go121      |
| Go        | Go 1.20     | 1st gen, 2nd gen | Ubuntu 22.04 | go120      |
| Go        | Go 1.19     | 1st gen, 2nd gen | Ubuntu 22.04 | go119      |
| Go        | Go 1.18     | 1st gen, 2nd gen | Ubuntu 22.04 | go118      |
| Go        | Go 1.16     | 1st gen, 2nd gen | Ubuntu 18.04 | go116      |
| Go        | Go 1.13     | 1st gen, 2nd gen | Ubuntu 18.04 | go113      |
| Go        | Go 1.11     | 1st gen, 2nd gen | Ubuntu 18.04 | go111      |
| Java      | Java 25     | 2nd gen          | Ubuntu 24.04 | java25     |
| Java      | Java 21     | 2nd gen          | Ubuntu 22.04 | java21     |
| Java      | Java 17     | 1st gen, 2nd gen | Ubuntu 22.04 | java17     |
| Java      | Java 11     | 1st gen, 2nd gen | Ubuntu 18.04 | java11     |
| Ruby      | Ruby 3.4    | 2nd gen          | Ubuntu 22.04 | ruby34     |
| Ruby      | Ruby 3.3    | 1st gen, 2nd gen | Ubuntu 22.04 | ruby33     |
| Ruby      | Ruby 3.2    | 1st gen, 2nd gen | Ubuntu 22.04 | ruby32     |
| Ruby      | Ruby 3.0    | 1st gen, 2nd gen | Ubuntu 18.04 | ruby30     |
| Ruby      | Ruby 2.7    | 1st gen, 2nd gen | Ubuntu 18.04 | ruby27     |
| Ruby      | Ruby 2.6    | 1st gen, 2nd gen | Ubuntu 18.04 | ruby26     |
| PHP       | PHP 8.4     | 2nd gen          | Ubuntu 22.04 | php84      |
| PHP       | PHP 8.3     | 2nd gen          | Ubuntu 22.04 | php83      |
| PHP       | PHP 8.2     | 1st gen, 2nd gen | Ubuntu 22.04 | php82      |
| PHP       | PHP 8.1     | 1st gen, 2nd gen | Ubuntu 18.04 | php81      |
| PHP       | PHP 7.4     | 1st gen, 2nd gen | Ubuntu 18.04 | php74      |
| .NET Core | .NET Core 8 | 2nd gen          | Ubuntu 22.04 | dotnet8    |
| .NET Core | .NET Core 6 | 1st gen, 2nd gen | Ubuntu 22.04 | dotnet6    |
| .NET Core | .NET Core 3 | 1st gen, 2nd gen | Ubuntu 18.04 | dotnet3    |

--------------------------------------------------------------------------------

## 5. Summary Checklist

Feature        | Best Practice
-------------- | -------------
**Base Image** | Use official, versioned, slim, or distroless images.
**Layers**     | Combine `RUN` commands; copy dependencies before source code.
**Security**   | Prefer not to run as `root`; never include secrets/ENV keys in Dockerfile.
**Size**       | Use **Multi-Stage builds** to strip out build-time bloat.
**Cloud Run**  | Listen on `0.0.0.0:${PORT:-8080}`; optionally use runtime base images.
**Metadata**   | Use `LABEL` to provide contact and versioning info.

#### Sources:

*   https://cloud.google.com/run/docs/configuring/services/automatic-base-image-updates
*   https://cloud.google.com/docs/buildpacks/base-images
*   https://cloud.google.com/run/docs/configuring/services/runtime-base-images
*   https://cloud.google.com/run/docs/building/containers
*   https://codelabs.developers.google.com/developing-containers-with-dockerfiles
*   https://docs.docker.com/get-started/docker-concepts/building-images/writing-a-dockerfile/
*   https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/
