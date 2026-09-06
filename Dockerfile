FROM ghcr.io/ggml-org/llama.cpp:full-rocm

WORKDIR /models

# Include /app in library search path for dynamic dependencies (.so files)
ENV LD_LIBRARY_PATH=/app:${LD_LIBRARY_PATH}

USER root
# Symlink binary to standard PATH
RUN ln -s /app/llama-server /usr/local/bin/llama-server && \
    chown -R 1001:0 /models && \
    chmod -R g+rwX /models

USER 1001

EXPOSE 8080
ENTRYPOINT ["llama-server"]