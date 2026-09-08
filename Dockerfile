FROM ghcr.io/ggml-org/llama.cpp:full-vulkan

WORKDIR /models

# Default ROCm runtime environment variables (overridable by OpenShift UI)
ENV HSA_OVERRIDE_GFX_VERSION=11.5.0 \
    HSA_ENABLE_SDMA=0 \
    HIP_VISIBLE_DEVICES=0 \
    ROCM_PATH=/opt/rocm \
    LD_LIBRARY_PATH=/app:${LD_LIBRARY_PATH} \
    HOME=/tmp \
    FLASH_ATTENTION=on

USER root

# Setup PATH and entrypoint permissions
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN ln -s /app/llama-server /usr/local/bin/llama-server && \
    chmod +x /usr/local/bin/entrypoint.sh && \
    chown -R 1001:0 /models /usr/local/bin/entrypoint.sh && \
    chmod -R g+rwX /models

USER 1001

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]