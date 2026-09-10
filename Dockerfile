FROM docker.io/rocm/migraphx-ci-ubuntu:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
        migraphx \
    && rm -rf /var/lib/apt/lists/*

# ONNX Runtime with MIGraphX EP from AMD
RUN pip install --no-cache-dir \
        --extra-index-url https://repo.radeon.com/rocm/manylinux/rocm-rel-6.4/ \
        onnxruntime-rocm

EXPOSE 8080
