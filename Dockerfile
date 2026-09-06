FROM ghcr.io/ggml-org/llama.cpp:server

WORKDIR /models

USER root
# Symlink or copy to standard PATH
RUN ln -s /app/llama-server /usr/local/bin/llama-server && \
    chown -R 1001:0 /models && \
    chmod -R g+rwX /models

USER 1001

EXPOSE 8080
ENTRYPOINT ["llama-server"]