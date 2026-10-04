# snuc-openshift-ai

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
(gfx1150), one GPU per node. Two constraints shape most decisions here.

### GPU memory per node

VRAM is carved out of system RAM in BIOS, so a larger reservation directly reduces
the memory available to pods on that node:

| Node | Dedicated VRAM | GTT | Allocatable RAM |
|---|---|---|---|
| snuc-01 | 32 GB | 30.9 GB | 62 GB |
| snuc-02 | 32 GB | 30.9 GB | 62 GB |
| snuc-03 | 48 GB | 23.0 GB | 46 GB |

Read from `/sys/class/drm/card0/device/mem_info_{vram,gtt}_total` on each node.
Note snuc-03 gives up 16 GB of pod-schedulable RAM for its larger carve-out, which is
enough to make 4 GiB requests fail to schedule there.

### ROCm does not work on these iGPUs

ONNX Runtime with `ROCMExecutionProvider` fails at startup with
`Hip error: 'out of memory'` in hipblaslt init. **This is not a VRAM sizing problem.**
It was tested directly on both a 32 GB node and the 48 GB node, at container memory
limits from 8 GiB to 12 GiB, and fails identically every time. The AMD GPU is
successfully allocated to the pod — the failure is inside hipblaslt on gfx1150.

Consequences:

- GGUF backends (llamacpp, lemonade) use **Vulkan**, which addresses shared system
  memory and works fine.
- ONNX vision models run on `onnxruntime-cpu`. The `onnxruntime-migraphx`
  ServingRuntime exists but is unused; note its image ships `ROCMExecutionProvider`
  and `CPUExecutionProvider` but **no** MIGraphX provider, so naming MIGraphX in
  `--providers` silently falls through to CPU while still holding a GPU.
- Pair CPU-runtime models with the `cpu-only` hardware profile so they do not reserve
  a GPU they cannot use.

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
