FROM ghcr.io/lemonade-sdk/lemonade-server:latest

USER root

# Configure ROCm backend for llamacpp
RUN mkdir -p /opt/lemonade/.config/lemonade && \
    echo '{"llamacpp": {"backend": "vulkan"}, "extra_models_dir": "/mnt/models"}' > /opt/lemonade/.config/lemonade/config.json && \
    chown -R 10001:0 /opt/lemonade/.config/lemonade

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    chown 10001:0 /usr/local/bin/entrypoint.sh

USER 10001

ENV HSA_OVERRIDE_GFX_VERSION=11.5.0 \
    HSA_ENABLE_SDMA=0 \
    HIP_VISIBLE_DEVICES=0

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
