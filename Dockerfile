# Stage 1: Pull MIGraphX + HIP libraries from AMD's ROCm image
FROM docker.io/rocm/migraphx-ci-ubuntu:latest AS rocm-libs

# Stage 2: Production UBI9 runtime
FROM registry.access.redhat.com/ubi9/python-312

USER 0

# Copy only required ROCm/MIGraphX shared libraries
COPY --from=rocm-libs /opt/rocm/lib/libmigraphx*.so* /opt/rocm/lib/
COPY --from=rocm-libs /opt/rocm/lib/libamdhip64*.so* /opt/rocm/lib/
COPY --from=rocm-libs /opt/rocm/lib/libhsa-runtime64*.so* /opt/rocm/lib/
COPY --from=rocm-libs /opt/rocm/lib/libamd_comgr*.so* /opt/rocm/lib/
COPY --from=rocm-libs /opt/rocm/lib/librocblas*.so* /opt/rocm/lib/
COPY --from=rocm-libs /opt/rocm/lib/libMIOpen*.so* /opt/rocm/lib/
COPY --from=rocm-libs /opt/rocm/lib/librocm_smi64*.so* /opt/rocm/lib/

ENV LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH}"

# ONNX Runtime with MIGraphX EP from AMD
RUN pip install --no-cache-dir \
        --extra-index-url https://repo.radeon.com/rocm/manylinux/rocm-rel-6.4/ \
        onnxruntime-rocm

USER 1001

EXPOSE 8080
