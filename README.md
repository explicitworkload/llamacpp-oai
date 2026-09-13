# Vision AI

Real-time object detection and instance segmentation pipeline for OpenShift AI. Captures an RTSP camera feed, runs inference through RF-DETR (detection) and SAM2 (segmentation) served via KServe, and streams annotated video with bounding boxes and segmentation masks.

## Architecture

```
┌──────────────┐    RTSP     ┌───────────────┐   KServe V2   ┌─────────────────────┐
│  TP-Link     │ ──────────▶ │  visionai-app │ ────────────▶ │  RF-DETR (KServe)   │
│  VIGI S245   │             │  (FastAPI)    │               │  Object Detection   │
│  RTSP Camera │             │               │               └─────────────────────┘
└──────────────┘             │  OpenCV       │   KServe V2   ┌─────────────────────┐
                             │  capture +    │ ────────────▶ │  SAM2 (KServe)      │
                             │  annotation   │               │  Segmentation Masks │
                             └───────────────┘               └─────────────────────┘
                                    │
                                    ▼
                             Annotated MJPEG stream / snapshots / JSON API
```

## Components

### ServingRuntime - ROCm/GPU (`Dockerfile`)

Custom KServe ServingRuntime image with ONNX Runtime + ROCm for AMD GPU.

- **Base**: `rocm/migraphx-ci-ubuntu`
- **Runtime**: ONNX Runtime with `ROCMExecutionProvider` (ROCm 6.4)

### ServingRuntime - CPU (`Dockerfile.cpu`)

CPU-only KServe ServingRuntime image with ONNX Runtime.

- **Base**: Red Hat UBI9
- **Runtime**: ONNX Runtime with `CPUExecutionProvider`

### Vision AI App (`app/Dockerfile`)

FastAPI application that captures RTSP frames and calls KServe inference endpoints.

- **Base**: Red Hat UBI9
- **Dependencies**: OpenCV, httpx, numpy, FastAPI

## Models

| Model | Purpose | License | Format |
|-------|---------|---------|--------|
| [RF-DETR](https://github.com/roboflow/rf-detr) (Base) | Object detection (COCO 80 classes) | Apache 2.0 | ONNX |
| [SAM2](https://github.com/facebookresearch/sam2) (Hiera Small) | Instance segmentation masks | Apache 2.0 | ONNX |

RF-DETR runs on AMD GPU via the `onnxruntime-migraphx` ServingRuntime. SAM2 runs on CPU via the `onnxruntime-cpu` ServingRuntime.

### Exporting RF-DETR to ONNX

```bash
pip install "rfdetr[onnx]"
python -c "
from rfdetr import RFDETRBase
model = RFDETRBase(pretrain_weights='coco')
model.export(format='onnx', output_dir='./rf-detr')
"
# Upload rf-detr/inference_model.onnx to S3 at /models/
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Status of detector, segmenter, and camera connection |
| `/detect` | POST | Upload an image, returns detection + segmentation JSON |
| `/detect/camera` | GET | Run detection on current RTSP frame (JSON) |
| `/snapshot` | GET | JPEG snapshot from camera with annotations |
| `/stream` | GET | Live MJPEG stream with detection overlay and segmentation masks |

## Prerequisites

- OpenShift cluster with OpenShift AI (RHOAI) installed
- AMD GPU node (`amd.com/gpu`) with ROCm drivers
- S3-compatible storage (e.g., OpenShift Data Foundation) with a data connection
- RTSP camera accessible from the cluster network
- Quay registry (in-cluster or external) for container images
- OpenShift GitOps (ArgoCD) operator installed
- OpenShift Pipelines (Tekton) operator installed

## Setup

### 1. Create namespaces

```bash
oc new-project visionai   # Tekton pipelines
oc new-project john        # InferenceServices and app
```

### 2. Create the S3 data connection and service account

Create a data connection in OpenShift AI pointing to your S3 bucket containing the ONNX models. This creates a secret named `models-odf-s3` and a service account that the InferenceServices use to pull model weights.

```bash
oc create sa models-odf-s3-sa -n john
```

The service account needs to be referenced in the InferenceService and vision-ai deployment specs.

### 3. Create the RTSP credentials secret

```bash
oc create secret generic rtsp-credentials \
  --from-literal=RTSP_URL='rtsp://<user>:<password>@<camera-ip>/stream1' \
  -n john
```

### 4. Create the Quay push secret for Tekton pipelines

The pipeline pushes built images to your Quay registry. Create the secret with your Quay credentials (do NOT commit real credentials to Git):

```bash
oc create secret docker-registry quay-push-secret \
  --docker-server=<quay-hostname> \
  --docker-username=<username> \
  --docker-password='<password>' \
  -n visionai
```

The placeholder in `pipelines/quay-secret.yaml` is for reference only.

### 5. Create the Red Hat pull secret (for Tekton tasks)

The `restart-rollouts` pipeline task uses `registry.redhat.io/openshift4/ose-cli`, which requires Red Hat registry authentication.

```bash
oc create secret generic pull-secret \
  --from-file=.dockerconfigjson=pull-secret.json \
  --type=kubernetes.io/dockerconfigjson \
  -n visionai

oc patch sa pipeline -n visionai -p '{"imagePullSecrets": [{"name": "pull-secret"}]}'
```

### 6. Create the GitHub webhook secret

Generate a secure secret for webhook validation:

```bash
SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
oc create secret generic github-webhook-secret \
  --from-literal=secret="$SECRET" \
  -n visionai
echo "Use this secret in your GitHub webhook config: $SECRET"
```

### 7. Upload model weights to S3

Place ONNX files in your S3 bucket:

```
/models/inference_model.onnx          # RF-DETR
/models/sam2_hiera_small.encoder.onnx # SAM2
```

### 8. Deploy with ArgoCD

Apply the ArgoCD Applications to sync manifests from Git:

```bash
oc apply -f argocd/application.yaml            # Watches k8s/ directory
oc apply -f argocd/application-pipelines.yaml   # Watches pipelines/ directory
```

ArgoCD will automatically deploy:
- ServingRuntimes (ROCm and CPU)
- InferenceServices (RF-DETR and SAM2)
- Vision AI app deployment, service, and route
- Tekton Pipeline definition and triggers

### 9. Configure GitHub webhook

In your GitHub repository settings, add a webhook:

- **Payload URL**: `https://<github-webhook-route>/`
- **Content type**: `application/json`
- **Secret**: the secret string from step 6
- **Events**: "Just the push event"

The CEL filter in the trigger only fires on pushes to `experiment/vision-ai`.

### 10. Run the initial pipeline build

```bash
oc create -f pipelines/pipelinerun.yaml -n visionai
```

This builds all three images (`:latest`, `:cpu`, `visionai-app:latest`) and restarts the deployments.

## Project Structure

```
Dockerfile                  # ServingRuntime image (ROCm + ONNX Runtime)
Dockerfile.cpu              # ServingRuntime image (CPU + ONNX Runtime)
serve.py                    # KServe model server (shared by both runtimes)
app/
  Dockerfile                # App image (UBI9 + OpenCV + FastAPI)
  main.py                   # FastAPI server and endpoints
  detector.py               # RF-DETR KServe client + annotation rendering
  segmenter.py              # SAM2 KServe client
  camera.py                 # Threaded RTSP capture
  requirements.txt          # Python dependencies
k8s/
  servingruntime-rocm.yaml  # KServe ServingRuntime CR (onnxruntime-migraphx)
  servingruntime-cpu.yaml   # KServe ServingRuntime CR (onnxruntime-cpu)
  inferenceservice.yaml     # KServe InferenceServices (RF-DETR + SAM2)
  vision-ai.yaml            # App Deployment, Service, Route
  vision-ai-rbac.yaml       # RBAC for app SA to access InferenceServices
  pipeline-rbac.yaml        # RBAC for pipeline SA to restart deployments
pipelines/
  pipeline.yaml             # Tekton Pipeline (clone, build x3, restart-rollouts)
  pipelinerun.yaml          # Manual PipelineRun template
  triggers.yaml             # EventListener, TriggerBinding, TriggerTemplate, Route
  quay-secret.yaml          # Quay push secret placeholder (do NOT commit real creds)
  workspace-pvc.yaml        # Shared PVC (unused, pipeline uses volumeClaimTemplate)
argocd/
  application.yaml          # ArgoCD Application for k8s/ manifests
  application-pipelines.yaml # ArgoCD Application for pipelines/ manifests
```

## Configuration

The vision-ai app is configured via environment variables in `k8s/vision-ai.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `INFERENCE_URL` | `https://rf-detr-predictor.<ns>.svc.cluster.local:8443` | RF-DETR predictor endpoint (HTTPS via kube-rbac-proxy) |
| `MODEL_NAME` | `model` | KServe model name for detection |
| `SAM2_URL` | `https://sam2-predictor.<ns>.svc.cluster.local:8443` | SAM2 predictor endpoint (HTTPS via kube-rbac-proxy) |
| `SAM2_MODEL_NAME` | `model` | KServe model name for segmentation |
| `RTSP_URL` | (from secret) | RTSP camera URL (via `rtsp-credentials` secret) |
| `INPUT_SIZE` | `640` | Detection model input resolution |
| `CONF_THRESHOLD` | `0.25` | Minimum confidence for detections |

## CI/CD

### Tekton Pipeline

The `vision-ai-build` pipeline runs on every push to `experiment/vision-ai` via GitHub webhook:

1. **clone** - Clones the repository
2. **build-serving** - Builds ROCm GPU image (`:latest`) ~30 min
3. **build-serving-cpu** - Builds CPU image (`:cpu`) ~5 min
4. **build-app** - Builds app image (`visionai-app:latest`) ~3 min
5. **restart-rollouts** - Restarts deployments to pick up new images

Each pipeline run creates an ephemeral PVC via `volumeClaimTemplate` that is cleaned up automatically.

### ArgoCD

Two ArgoCD Applications watch the `experiment/vision-ai` branch:

- `vision-ai` - syncs `k8s/` manifests (auto-sync, prune, self-heal)
- `vision-ai-pipelines` - syncs `pipelines/` manifests (excludes `quay-secret.yaml`)

### Manual build

```bash
# ServingRuntime (ROCm)
podman build -t <registry>/visionai:latest .

# ServingRuntime (CPU)
podman build -f Dockerfile.cpu -t <registry>/visionai:cpu .

# App
podman build -f app/Dockerfile -t <registry>/visionai-app:latest .
```
