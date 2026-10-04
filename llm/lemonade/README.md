# llamacpp-oai

> **Branch: `experiment/lemonade-rocm`** — This is an experimental branch exploring [Lemonade](https://github.com/lemonade-sdk/lemonade) as an alternative backend to llama.cpp. The `main` branch contains the original llama.cpp-based deployment.

Deploy Lemonade as an OpenAI-compatible inference server on OpenShift AI using KServe.

## Overview

This project provides a container image and KServe manifests to serve GGUF models via Lemonade on OpenShift AI with AMD GPU acceleration (Vulkan). The entrypoint automatically discovers a `.gguf` model file from the KServe model mount path, registers it with the InferenceService name as an alias, and starts `lemond` with an OpenAI-compatible API on port 8080.

## Prerequisites

- OpenShift cluster with OpenShift AI (Open Data Hub) installed
- AMD GPU nodes available in the cluster
- S3-compatible object storage (e.g., OpenShift Data Foundation) with GGUF model files uploaded
- A data connection (`odf-s3`) configured in your namespace

## Project Structure

```
Dockerfile              # Container image based on lemonade-server
entrypoint.sh           # Auto-discovers GGUF model, registers KServe alias, starts lemond
servingruntime.yaml     # KServe ServingRuntime for Lemonade
inferenceservice.yaml   # KServe InferenceService example
```

## Building the Image

```bash
podman build -t quay.io/<your-user>/llamacpp:experiment_lemonade-rocm .
podman push quay.io/<your-user>/llamacpp:experiment_lemonade-rocm
```

## Deploying on OpenShift AI

### 1. Create the ServingRuntime

Update the `namespace` and `image` fields in [servingruntime.yaml](servingruntime.yaml), then apply:

```bash
oc apply -f servingruntime.yaml
```

### 2. Create the InferenceService

Update the `namespace` and `storage.path` fields in [inferenceservice.yaml](inferenceservice.yaml) to point to your GGUF model in S3, then apply:

```bash
oc apply -f inferenceservice.yaml
```

### 3. Test the Endpoint

Once the inference service is ready:

```bash
# Get the inference endpoint
URL=$(oc get inferenceservice llamalemonade -o jsonpath='{.status.url}')

# List available models
curl $URL/v1/models

# Chat completion
curl $URL/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llamalemonade",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Configuration

### Lemonade Config

The Dockerfile bakes in `/opt/lemonade/.config/lemonade/config.json` with:

| Setting | Value | Description |
|---|---|---|
| `llamacpp.backend` | `vulkan` | GPU backend for llama.cpp |
| `extra_models_dir` | `/tmp/models` | Directory scanned for GGUF models (symlinked from /mnt/models) |

### Why Vulkan instead of ROCm?

This branch was originally intended to use ROCm, but during testing on an AMD Ryzen AI 9 HX 370 (Radeon 890M iGPU, gfx1150), the ROCm backend failed with out-of-memory errors. The iGPU has only 512 MB of dedicated VRAM by default (configurable in BIOS), and the ROCm/HIP runtime could not allocate within that limit — even with a small context size.

Vulkan handles APU shared memory differently, accessing the full system RAM pool (~47 GB) without needing a large dedicated VRAM carve-out. This makes it the practical choice for iGPU deployments. ROCm may work after increasing the iGPU VRAM allocation in BIOS to 4-8 GB.

### Environment Variables

The Dockerfile sets the following defaults (carried over from ROCm experimentation, harmless with Vulkan):

| Variable | Default | Description |
|---|---|---|
| `HSA_OVERRIDE_GFX_VERSION` | `11.5.0` | Override GPU architecture version |
| `HSA_ENABLE_SDMA` | `0` | Disable SDMA (required for some iGPUs) |
| `HIP_VISIBLE_DEVICES` | `0` | GPU device index to use |

### KServe Model Name Alias

The entrypoint automatically registers the GGUF model under the InferenceService name (derived from the pod hostname). This allows the OpenShift AI playground and KServe clients to reference the model by InferenceService name without needing to know the GGUF filename.

## Branches

| Branch | Backend | Description |
|---|---|---|
| `main` | llama.cpp (Vulkan) | Original llama.cpp deployment |
| `experiment/lemonade-rocm` | Lemonade (Vulkan) | Lemonade-based deployment with Vulkan GPU acceleration |
