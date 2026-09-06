# llamacpp-oai

Deploy [llama.cpp](https://github.com/ggml-org/llama.cpp) as an OpenAI-compatible inference server on OpenShift AI using KServe.

## Overview

This project provides a container image and KServe manifests to serve GGUF models via llama.cpp on OpenShift AI with AMD GPU acceleration (ROCm). The entrypoint automatically discovers a `.gguf` model file from the KServe model mount path and starts `llama-server` with an OpenAI-compatible API on port 8080.

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
URL=$(oc get inferenceservice llamacpp -o jsonpath='{.status.url}')

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

### ROCm Environment Variables

The Dockerfile sets the following defaults, which can be overridden at deploy time:

| Variable | Default | Description |
|---|---|---|
| `HSA_OVERRIDE_GFX_VERSION` | `11.5.0` | Override GPU architecture version |
| `HSA_ENABLE_SDMA` | `0` | Disable SDMA (required for some iGPUs) |
| `HIP_VISIBLE_DEVICES` | `0` | GPU device index to use |

### llama-server Arguments

Additional arguments can be passed to `llama-server` via the container command in [servingruntime.yaml](servingruntime.yaml). Common options:

| Flag | Description |
|---|---|
| `-ngl <N>` | Number of layers to offload to GPU |
| `-fa off` | Disable flash attention (needed for some iGPUs) |
| `--device ROCm0` | Select the ROCm device |
| `-c <N>` | Context size |
