FROM registry-quay-app.quay.svc.cluster.local/visionai/visionai:rocm-base

COPY serve.py /opt/serve.py

ENTRYPOINT ["python3", "/opt/serve.py"]
