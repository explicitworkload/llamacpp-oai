FROM registry.access.redhat.com/ubi9/python-312

USER 0

# AMD ROCm + MIGraphX
RUN echo -e '[ROCm-6.4]\n\
name=AMD ROCm 6.4\n\
baseurl=https://repo.radeon.com/rocm/rhel9/6.4/main\n\
enabled=1\n\
gpgcheck=1\n\
gpgkey=https://repo.radeon.com/rocm/rocm.gpg.key' \
    > /etc/yum.repos.d/rocm.repo \
    && dnf install -y --nodocs \
        rocm-hip-runtime \
        migraphx \
    && dnf clean all

# ONNX Runtime with MIGraphX EP from AMD
RUN pip install --no-cache-dir \
        --index-url https://repo.radeon.com/rocm/manylinux/rocm-rel-6.4/ \
        onnxruntime-rocm

USER 1001

EXPOSE 8080
