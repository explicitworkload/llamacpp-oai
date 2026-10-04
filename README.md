# snuc-openshift-ai

AI inference and tooling running on a three-node SNUC cluster under OpenShift AI.

This is a homelab-scale cluster of AMD Ryzen AI mini PCs, and that shapes almost
everything in here. There are no discrete GPUs — just one Radeon 890M integrated GPU
per node, sharing system RAM. Which accelerator backend works, how much memory a pod
may request, and which models can be served at all are decided by that hardware, not
by preference. Those constraints are documented in [Hardware Notes](#hardware-notes);
read them before adding a workload.

## The Cluster

OpenShift 4.21 with OpenShift AI (Open Data Hub), three nodes, RHEL CoreOS 9.6.

| | snuc-01 | snuc-02 | snuc-03 |
|---|---|---|---|
| CPU | 24 vCPU (23.5 allocatable) | 24 vCPU | 24 vCPU |
| System RAM | 62 GB allocatable | 62 GB | 46 GB |
| GPU | Radeon 890M | Radeon 890M | Radeon 890M |
| Dedicated VRAM | 32 GB | 32 GB | 48 GB |

Every node is an AMD Ryzen AI 9 HX 370 with a Radeon 890M iGPU (gfx1150, 16 CU).
One GPU each, so **three GPUs total** — which is the binding constraint on how many
accelerated workloads can run at once.

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

### VRAM is taken from system RAM

The 890M has no memory of its own. Dedicated VRAM is carved out of system RAM in
BIOS, so raising it directly reduces what pods can request on that node. snuc-03's
48 GB carve-out costs it 16 GB of schedulable RAM (46 GB vs 62 GB elsewhere) — enough
that a 4 GiB pod request no longer fits there.

Current GTT is 30.9 GB on snuc-01/02 and 23.0 GB on snuc-03. Read these per node with:

```bash
cat /sys/class/drm/card0/device/mem_info_vram_total   # dedicated VRAM
cat /sys/class/drm/card0/device/mem_info_gtt_total    # GTT (shared)
```

Since ROCm does not work here anyway (below), a larger VRAM reservation currently
buys nothing and only costs schedulable RAM.

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

## Reproducing Elsewhere

The manifests assume this cluster, so expect to adjust. You need:

- OpenShift with OpenShift AI (Open Data Hub) installed
- S3-compatible object storage (e.g., OpenShift Data Foundation) for model artifacts,
  with a data connection (`odf-s3`) in your namespace
- An accelerator, if you want one that works — on **discrete** AMD or NVIDIA GPUs the
  ROCm limitation above does not apply, and the `onnxruntime-migraphx` runtime and
  `amd-gpu-vision` hardware profile become usable as written

Namespaces are hardcoded (`john` for workloads, `visionai` for pipelines), as are the
Quay registry hostnames in each ServingRuntime and pipeline.
