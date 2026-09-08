# llamacpp-oai

> **Experimental branch available:** [`experiment/lemonade-rocm`](../../tree/experiment/lemonade-rocm) explores using [Lemonade](https://github.com/lemonade-sdk/lemonade) as an alternative backend with Vulkan GPU acceleration. See that branch's README for details.

Deploy [llama.cpp](https://github.com/ggml-org/llama.cpp) as an OpenAI-compatible inference server on OpenShift AI using KServe.

## Overview

This project provides a container image and KServe manifests to serve GGUF models via llama.cpp on OpenShift AI with AMD GPU acceleration (Vulkan). The entrypoint automatically discovers a `.gguf` model file from the KServe model mount path and starts `llama-server` with an OpenAI-compatible API on port 8080.

Optionally, the `web/` directory includes **Command Center** — a web UI for managing and chatting with multiple AI models from a single interface. It integrates with KServe InferenceServices and external OpenAI-compatible endpoints registered as AI asset endpoints. Command Center is designed for Red Hat OpenShift AI (tested on v3.5+).

## Prerequisites

- OpenShift cluster with OpenShift AI (Open Data Hub) installed
- AMD GPU nodes available in the cluster
- S3-compatible object storage (e.g., OpenShift Data Foundation) with GGUF model files uploaded
- A data connection (`odf-s3`) configured in your namespace

## Project Structure

```
Dockerfile              # Container image based on llama.cpp full-vulkan
entrypoint.sh           # Auto-discovers and launches the GGUF model
servingruntime.yaml     # KServe ServingRuntime for llama.cpp
inferenceservice.yaml   # KServe InferenceService example
web/                    # Command Center web application
  main.py               # FastAPI backend (auth, model proxy, transcription)
  Dockerfile            # Container image for Command Center
  requirements.txt      # Python dependencies
  static/               # Frontend (HTML, CSS, JS)
  k8s/deployment.yaml   # OpenShift deployment manifests (RBAC, Deployment, Service, Route)
```

## Building the Image

```bash
podman build -t quay.io/<your-user>/llamacpp:latest .
podman push quay.io/<your-user>/llamacpp:latest
```

## Deploying on OpenShift AI

### 1. Create the ServingRuntime

Update the `namespace` and `image` fields in [servingruntime.yaml](servingruntime.yaml), then apply:

```bash
oc apply -f servingruntime.yaml
```

This registers a `llamacpp` runtime that supports the `gguf` model format with AMD GPU acceleration.

### 2. Create the InferenceService

Update the `namespace` and `storage.path` fields in [inferenceservice.yaml](inferenceservice.yaml) to point to your GGUF model in S3, then apply:

```bash
oc apply -f inferenceservice.yaml
```

### 3. Test the Endpoint

Once the inference service is ready:

```bash
# Get the inference endpoint
URL=$(oc get inferenceservice qwen35-4b -o jsonpath='{.status.url}')

# List available models
curl $URL/v1/models

# Chat completion
curl $URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "default",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Configuration

### Runtime Environment Variables

The entrypoint supports the following environment variables, which can be set as defaults in [servingruntime.yaml](servingruntime.yaml) or overridden per-model in [inferenceservice.yaml](inferenceservice.yaml):

| Variable | Default | Description |
|---|---|---|
| `CONTEXT_LENGTH` | `2048` | Context window size (`-c`). Higher values use more memory for the KV cache. |
| `N_GPU_LAYERS` | `99` | Number of layers to offload to GPU (`-ngl`). |
| `REASONING_BUDGET` | `1024` | Max thinking tokens for reasoning models (`--reasoning-budget`). Set to `0` to disable. |
| `FLASH_ATTENTION` | off | Set to `"on"` to enable flash attention (`-fa`). Leave off for iGPUs. |
| `EXTRA_ARGS` | *(empty)* | Additional flags passed to `llama-server`. |

To override per-model, add an `env` block in the InferenceService:

```yaml
spec:
  predictor:
    model:
      env:
        - name: CONTEXT_LENGTH
          value: "4096"
        - name: REASONING_BUDGET
          value: "0"
```

### ROCm Environment Variables

The Dockerfile sets the following defaults for ROCm compatibility:

| Variable | Default | Description |
|---|---|---|
| `HSA_OVERRIDE_GFX_VERSION` | `11.5.0` | Override GPU architecture version |
| `HSA_ENABLE_SDMA` | `0` | Disable SDMA (required for some iGPUs) |
| `HIP_VISIBLE_DEVICES` | `0` | GPU device index to use |

### Thinking Models

Models like Qwen3.5 generate internal `<think>` blocks before responding, which consumes extra context and memory. To control this:

- **Disable at the API level:** Add `/no_think` to the system prompt or user message.
- **Limit at the server level:** Set `EXTRA_ARGS` to `"--reasoning-budget 1024"` (or `0` to disable) if your llama.cpp build supports it.

## Command Center

The `web/` directory contains **Command Center** — a centralized web UI for managing and chatting with multiple AI models from a single interface.

### Features

- **Unified chat interface** for KServe InferenceServices and external OpenAI-compatible endpoints
- **External endpoint support** via a ConfigMap (`gen-ai-aa-custom-model-endpoints`) that defines providers, models, and API key references
- **Image upload** for vision-capable models (sent as base64 `image_url` content parts)
- **Audio upload** for transcription-capable models (transcribed via Whisper, transcript included in chat)
- **Streaming responses** with real-time stats (TTFT, tokens/sec, prompt tokens)
- **Markdown rendering** in responses (bold, italic, headers, lists, code blocks)
- **Auto-refresh** model status every 30 seconds

### Deploying Command Center

#### 1. Build and push the image

```bash
cd web
podman build -t quay.io/<your-user>/command-center:latest .
podman push quay.io/<your-user>/command-center:latest
```

#### 2. Deploy to OpenShift

Update the `image` and `namespace` in `web/k8s/deployment.yaml`, then apply:

```bash
oc apply -f web/k8s/deployment.yaml
```

This creates a ServiceAccount, RBAC Role (read access to InferenceServices, ConfigMaps, and Secrets), Deployment, Service, and Route.

#### 3. Add external endpoints (optional)

Create a ConfigMap to register external OpenAI-compatible providers:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gen-ai-aa-custom-model-endpoints
data:
  config.yaml: |
    providers:
      inference:
      - provider_id: my-provider
        provider_type: remote::openai
        config:
          base_url: https://api.example.com/openai/v1
          custom_gen_ai:
            api_key:
              secretRef:
                name: my-api-key-secret
                key: api_key
    registered_resources:
      models:
      - provider_id: my-provider
        model_id: model-name
        model_type: llm
        metadata:
          display_name: My Model
          capabilities:
          - text-generation
          - vision              # enables image upload
          - audio-transcription # enables audio upload
```

Create the corresponding Secret for the API key:

```bash
oc create secret generic my-api-key-secret --from-literal=api_key=<YOUR_API_KEY>
```

## Branches

| Branch | Backend | Description |
|---|---|---|
| `main` | llama.cpp (Vulkan) | Original llama.cpp deployment |
| `experiment/lemonade-rocm` | Lemonade (Vulkan) | Lemonade-based deployment with Vulkan GPU acceleration |
