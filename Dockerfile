# Stage 1: Pull MIGraphX + HIP libraries from AMD's ROCm image
FROM rocm/migraphx:latest AS rocm-libs

# Stage 2: Production UBI9 runtime
FROM registry.access.redhat.com/ubi9/python-312

USER 0

# Copy ROCm + MIGraphX shared libraries from AMD image
COPY --from=rocm-libs /opt/rocm /opt/rocm
ENV PATH="/opt/rocm/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH}"

# ONNX Runtime with MIGraphX EP from AMD
RUN pip install --no-cache-dir \
        --extra-index-url https://repo.radeon.com/rocm/manylinux/rocm-rel-6.4/ \
        onnxruntime-rocm

USER 1001

EXPOSE 8080
