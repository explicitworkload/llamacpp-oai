# llamacpp-oai

A monorepo of AI inference and tooling components deployed on OpenShift AI.

## Components

| Component | Description |
|---|---|
| [llm/llamacpp](llm/llamacpp/) | [llama.cpp](https://github.com/ggml-org/llama.cpp) as an OpenAI-compatible KServe inference server, with AMD GPU acceleration (Vulkan). |
| [llm/lemonade](llm/lemonade/) | [Lemonade](https://github.com/lemonade-sdk/lemonade) as an alternative inference backend, also with Vulkan GPU acceleration. |
| [litellm](litellm/) | [LiteLLM](https://github.com/BerriAI/litellm) proxy deployment with Postgres, for routing to external model providers. |
| [command-center](command-center/) | Web UI for managing and chatting with multiple AI models from a single interface. |
| [vision-ai](vision-ai/) | Real-time object detection and segmentation service (YOLOX / RF-DETR / SAM2) with a streaming web app. |

## Repository Layout

```
llm/
  llamacpp/        # llama.cpp serving runtime + KServe manifests
  lemonade/        # Lemonade serving runtime + KServe manifests
litellm/           # LiteLLM proxy manifests
command-center/    # Web UI (app, k8s/, pipelines/)
vision-ai/         # Vision inference (app/, k8s/, pipelines/, argocd/)
```

Each component owns its own `k8s/` manifests, `pipelines/`, and README. See the component README for build and deployment instructions.

## Prerequisites

- OpenShift cluster with OpenShift AI (Open Data Hub) installed
- GPU nodes available for the inference components
- S3-compatible object storage (e.g., OpenShift Data Foundation) for model artifacts
