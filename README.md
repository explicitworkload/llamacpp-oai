# llamacpp-oai

A monorepo of AI inference and tooling components deployed on OpenShift AI (Open Data Hub),
targeting an AMD Ryzen AI / Radeon iGPU cluster.

## Components

| Component | Description |
|---|---|
| [llm/llamacpp](llm/llamacpp/) | [llama.cpp](https://github.com/ggml-org/llama.cpp) as an OpenAI-compatible KServe inference server, Vulkan GPU acceleration. |
| [llm/lemonade](llm/lemonade/) | [Lemonade](https://github.com/lemonade-sdk/lemonade) as an alternative GGUF backend, also Vulkan. |
| [litellm](litellm/) | [LiteLLM](https://github.com/BerriAI/litellm) proxy + Postgres, for routing to external model providers. |
| [command-center](command-center/) | Web UI for managing and chatting with multiple AI models from one interface. |
| [vision-ai](vision-ai/) | Real-time object detection and instance segmentation (YOLO26) with a streaming web app. |

## Architecture

```
                        ┌──────────────────────────────────────────┐
                        │            command-center                │
                        │     FastAPI + static UI, model proxy     │
                        └───────┬─────────────────────┬────────────┘
                                │                     │
                     KServe ISVc│                     │OpenAI-compatible
                      discovery │                     │  (external models)
                                ▼                     ▼
        ┌───────────────────────────────────┐   ┌──────────────┐
        │        KServe InferenceServices   │   │   litellm    │
        │                                   │   │    proxy     │
        │  llamacpp  │ lemonade │  YOLO26   │   └──────────────┘
        │   (GGUF)   │  (GGUF)  │  (ONNX)   │
        └───────────────────────────────────┘
                                 ▲
                           gRPC  │ :8001
                                 │
   ┌──────────────┐      ┌───────┴────────┐
   │ RTSP camera  │─────▶│  vision-ai app │─────▶ annotated MJPEG stream,
   │ / video file │      │ OpenCV+FastAPI │       snapshots, JSON API
   └──────────────┘      └────────────────┘
```

Each component owns its own `k8s/` manifests, `pipelines/`, and README. The component
README is authoritative for build and deployment steps.

## Serving Stack

### LLM serving (GGUF)

Two interchangeable backends serve GGUF models through KServe with an OpenAI-compatible
API on port 8080. Both auto-discover a `.gguf` file from the KServe model mount path.

| | llamacpp | lemonade |
|---|---|---|
| Server | `llama-server` | `lemond` |
| Acceleration | Vulkan | Vulkan |
| Model alias | filename | registered under the InferenceService name |

Tunables (`CONTEXT_LENGTH`, `N_GPU_LAYERS`, `REASONING_BUDGET`, `FLASH_ATTENTION`,
`EXTRA_ARGS`) are set as ServingRuntime defaults and overridable per-model on the
InferenceService. See [llm/llamacpp](llm/llamacpp/#configuration).

### Vision serving (ONNX)

YOLO26 models served via KServe, consumed over gRPC by the vision-ai app.

| Model | Purpose | Runtime |
|---|---|---|
| YOLO26m | Object detection (COCO 80 classes) | `onnxruntime-cpu` |
| YOLO26n-seg | Detection + instance segmentation | `onnxruntime-cpu` |

An `onnxruntime-migraphx` ServingRuntime also exists for GPU inference, but is not
currently in use — see the hardware note below.

## Hardware Notes

The cluster runs AMD Ryzen AI 9 HX 370 nodes with Radeon 890M integrated GPUs
(gfx1150), one GPU per node. Two constraints shape most decisions here:

**ROCm/HIP cannot allocate on these iGPUs out of the box.** The 890M carves out only
512 MB of dedicated VRAM by default, and the HIP runtime fails with out-of-memory
inside that limit — even at small context sizes. This is why the GGUF backends use
Vulkan, which addresses the full shared system RAM pool instead of a dedicated
carve-out. The same failure appears in ONNX Runtime as
`Hip error: 'out of memory'` in hipblaslt init when using `ROCMExecutionProvider`.
Raising the container memory limit does not help, since the ceiling is the BIOS VRAM
allocation, not the cgroup. Increasing the iGPU VRAM reservation to 4-8 GB in BIOS is
the documented path to making ROCm viable.

**Hardware profiles can force a GPU request.** OpenShift AI's `default-profile`
declares `amd.com/gpu` with `minCount: 1`, so any InferenceService referencing it
reserves a GPU whether or not its runtime can use one. Models on a CPU runtime should
use the `cpu-only` profile instead. Note that a GPU request already injected into a
stored InferenceService spec will not be removed by `kubectl apply` (map keys merge);
it has to be stripped with a JSON patch.

## Repository Layout

```
llm/
  llamacpp/        # llama.cpp serving runtime + KServe manifests
  lemonade/        # Lemonade serving runtime + KServe manifests
litellm/           # LiteLLM proxy manifests
command-center/    # Web UI (app, k8s/, pipelines/)
vision-ai/         # Vision inference (app/, k8s/, pipelines/, argocd/, hardware-profiles/)
audio-samples/     # Shared test fixtures
video-samples/
```

## CI/CD

Tekton pipelines build each component and restart its deployment; ArgoCD syncs the
`k8s/` manifests. A shared `github-listener` EventListener in the `visionai` namespace
routes pushes to the right pipeline by branch.

## Prerequisites

- OpenShift cluster with OpenShift AI (Open Data Hub) installed
- AMD GPU nodes for the inference components
- S3-compatible object storage (e.g., OpenShift Data Foundation) for model artifacts
- A data connection (`odf-s3`) configured in your namespace
