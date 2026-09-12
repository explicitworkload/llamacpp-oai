FROM docker.io/rocm/migraphx-ci-ubuntu:latest

RUN pip install --no-cache-dir --ignore-installed \
        --extra-index-url https://repo.radeon.com/rocm/manylinux/rocm-rel-6.4/ \
        onnxruntime-rocm kserve numpy

COPY serve.py /opt/serve.py

EXPOSE 8080

ENTRYPOINT ["python", "/opt/serve.py"]
