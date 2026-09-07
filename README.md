# llamacpp-oai

> **Experimental branch available:** [`experiment/lemonade-rocm`](../../tree/experiment/lemonade-rocm) explores using [Lemonade](https://github.com/lemonade-sdk/lemonade) as an alternative backend with Vulkan GPU acceleration. See that branch's README for details.

Deploy [llama.cpp](https://github.com/ggml-org/llama.cpp) as an OpenAI-compatible inference server on OpenShift AI using KServe.

## Overview

This project provides a container image and KServe manifests to serve GGUF models via llama.cpp on OpenShift AI with AMD GPU acceleration (Vulkan). The entrypoint automatically discovers a `.gguf` model file from the KServe model mount path and starts `llama-server` with an OpenAI-compatible API on port 8080.

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
| `FLASH_ATTENTION` | off | Set to `"on"` to enable flash attention (`-fa`). Leave off for iGPUs. |
| `EXTRA_ARGS` | *(empty)* | Additional flags passed to `llama-server` (e.g., `--reasoning-budget 0`). |

To override per-model, add an `env` block in the InferenceService:

```yaml
spec:
  predictor:
    model:
      env:
        - name: CONTEXT_LENGTH
          value: "4096"
        - name: EXTRA_ARGS
          value: "--reasoning-budget 0"
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

## Branches

| Branch | Backend | Description |
|---|---|---|
| `main` | llama.cpp (Vulkan) | Original llama.cpp deployment |
| `experiment/lemonade-rocm` | Lemonade (Vulkan) | Lemonade-based deployment with Vulkan GPU acceleration |
