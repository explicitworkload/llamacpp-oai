apiVersion: serving.kserve.io/v1alpha1
kind: ServingRuntime
metadata:
  name: llama-cpp-modelcar-runtime
  namespace: redhat-ods-applications
  labels:
    opendatahub.io/dashboard: "true"
spec:
  annotations:
    prometheus.io/port: "8080"
    prometheus.io/path: "/metrics"
  builtInAdapter:
    memBufferBytes: 134217728
    modelLoadingTimeoutMillis: 900000
  supportedModelFormats:
    - name: gguf
      version: "1"
      autoSelect: true
  containers:
    - name: kserve-container
      image: quay.apps.snuc.kubernetes.day/models/llama-cpp-runtime:latest
      command:
        - /bin/sh
        - -c
        - |
          echo "Scanning /mnt/models for Modelcar GGUF files..."
          
          # Recursively locate any .gguf file extracted from quay.io/jgoh/llamacpp:latest
          MODEL_FILE=$(find /mnt/models -type f -name "*.gguf" | head -n 1)
          
          if [ -z "$MODEL_FILE" ]; then
            echo "ERROR: No .gguf file found under /mnt/models!"
            echo "Current directory tree contents:"
            ls -laR /mnt/models
            exit 1
          fi
          
          echo "Found model file: $MODEL_FILE"
          exec /llama-server -m "$MODEL_FILE" --host 0.0.0.0 --port 8080 -fa -ngl 99 --alias default
      ports:
        - containerPort: 8080
          name: http1
          protocol: TCP
      resources:
        requests:
          cpu: "2"
          memory: 4Gi
          amd.com/gpu: "1"
        limits:
          cpu: "4"
          memory: 8Gi
          amd.com/gpu: "1"
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
        runAsNonRoot: true