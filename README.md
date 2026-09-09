# Vision AI

Real-time object detection and instance segmentation pipeline for OpenShift AI. Captures an RTSP camera feed, runs inference through RF-DETR (detection) and SAM2 (segmentation) served via KServe, and streams annotated video with bounding boxes and segmentation masks.

## Architecture

```
┌──────────────┐    RTSP     ┌───────────────┐   KServe V2   ┌─────────────────────┐
│  TP-Link     │ ──────────▶ │  visionai-app │ ────────────▶ │  RF-DETR (KServe)   │
│  VIGI S245   │             │  (FastAPI)    │               │  Object Detection   │
│  RTSP Camera │             │               │               └─────────────────────┘
└──────────────┘             │  GStreamer     │   KServe V2   ┌─────────────────────┐
                             │  capture +    │ ────────────▶ │  SAM2 (KServe)      │
                             │  annotation   │               │  Segmentation Masks │
                             └───────────────┘               └─────────────────────┘
                                    │
                                    ▼
                             Annotated MJPEG stream / snapshots / JSON API
```

## Components

### ServingRuntime (`Dockerfile`)

Custom KServe ServingRuntime image with ONNX Runtime + MIGraphX on AMD GPU.

- **Base**: Red Hat UBI9
- **Runtime**: ONNX Runtime with `MIGraphXExecutionProvider` (ROCm 6.4)
- **Image**: `quay.io/jgoh/vision-ai:latest`

### Vision AI App (`app/Dockerfile`)

FastAPI application that captures RTSP frames and calls KServe inference endpoints.

- **Base**: Red Hat UBI9
- **RTSP**: OpenCV built with GStreamer (low-latency pipeline with `rtspsrc`)
- **Image**: `quay.io/jgoh/visionai-app:latest`

## Models

| Model | Purpose | License | Format |
|-------|---------|---------|--------|
| [RF-DETR](https://github.com/roboflow/rf-detr) (Base) | Object detection (COCO 80 classes) | Apache 2.0 | ONNX |
| [SAM2](https://github.com/facebookresearch/sam2) (Hiera Small) | Instance segmentation masks | Apache 2.0 | ONNX |

Both models are served on AMD GPU via KServe InferenceServices using the custom `onnxruntime-migraphx` ServingRuntime.

### Exporting RF-DETR to ONNX

```bash
pip install "rfdetr[onnx]"
python -c "
from rfdetr import RFDETRBase
model = RFDETRBase(pretrain_weights='coco')
model.export(format='onnx', output_dir='./rf-detr')
"
# Upload rf-detr/inference_model.onnx to S3 at /models/rf-detr/
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

- OpenShift cluster with OpenShift AI installed
- AMD GPU node (`amd.com/gpu`) with ROCm drivers
- S3-compatible storage (e.g., OpenShift Data Foundation) with a `models-odf-s3` data connection
- RTSP camera accessible from the cluster network

## Deployment

### 1. Upload model weights to S3

Place ONNX files in your S3 bucket:

```
/models/rf-detr/inference_model.onnx
/models/sam2/sam2_hiera_small.onnx
```

### 2. Deploy the ServingRuntime and InferenceServices

```bash
oc apply -f k8s/servingruntime-rocm.yaml
oc apply -f k8s/inferenceservice.yaml
```

### 3. Deploy the Vision AI app

Update the `INFERENCE_URL` and `SAM2_URL` environment variables in `k8s/vision-ai.yaml` to match your InferenceService routes, then:

```bash
oc apply -f k8s/vision-ai.yaml
```

## Project Structure

```
Dockerfile                  # ServingRuntime image (UBI9 + ROCm + MIGraphX + ONNX Runtime)
app/
  Dockerfile                # App image (UBI9 + GStreamer + OpenCV + FastAPI)
  main.py                   # FastAPI server and endpoints
  detector.py               # RF-DETR KServe client + annotation rendering
  segmenter.py              # SAM2 KServe client
  camera.py                 # Threaded RTSP capture via GStreamer
k8s/
  servingruntime-rocm.yaml  # KServe ServingRuntime CR (onnxruntime-migraphx)
  inferenceservice.yaml     # KServe InferenceServices (RF-DETR + SAM2)
  vision-ai.yaml            # App Deployment, Service, Route
requirements.txt            # Python dependencies for the app
```

## Configuration

The app is configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `INFERENCE_URL` | `https://rf-detr-john.apps.example.com` | RF-DETR KServe endpoint |
| `MODEL_NAME` | `rf-detr` | KServe model name for detection |
| `SAM2_URL` | `https://sam2-john.apps.example.com` | SAM2 KServe endpoint |
| `SAM2_MODEL_NAME` | `sam2` | KServe model name for segmentation |
| `RTSP_URL` | `rtsp://172.16.199.10:554/stream1` | RTSP camera URL |
| `INPUT_SIZE` | `640` | Detection model input resolution |
| `CONF_THRESHOLD` | `0.25` | Minimum confidence for detections |

## CI

| Image | Build Context | Dockerfile |
|-------|---------------|------------|
| `quay.io/jgoh/vision-ai:latest` | `/` | `Dockerfile` |
| `quay.io/jgoh/visionai-app:latest` | `/` | `app/Dockerfile` |

```bash
# ServingRuntime
docker build -t quay.io/jgoh/vision-ai:latest .

# App
docker build -f app/Dockerfile -t quay.io/jgoh/visionai-app:latest .
```
