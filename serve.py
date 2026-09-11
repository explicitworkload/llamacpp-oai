import argparse
import glob
import os

import kserve
import numpy as np
import onnxruntime as ort
from kserve.protocol.rest.v2_datamodels import InferRequest


class ONNXModel(kserve.Model):
    def __init__(self, name: str, model_dir: str, providers: list[str]):
        super().__init__(name)
        self.model_dir = model_dir
        self.providers = providers
        self.session: ort.InferenceSession | None = None

    def load(self):
        model_files = glob.glob(os.path.join(self.model_dir, "**", "*.onnx"), recursive=True)
        if not model_files:
            raise FileNotFoundError(f"No .onnx file found in {self.model_dir}")
        self.session = ort.InferenceSession(model_files[0], providers=self.providers)
        self.ready = True

    def predict(self, payload: InferRequest | dict, headers: dict | None = None) -> dict:
        if isinstance(payload, InferRequest):
            payload = payload.model_dump()

        inputs = {}
        for inp in payload.get("inputs", []):
            dtype = _kserve_dtype_to_numpy(inp.get("datatype", "FP32"))
            inputs[inp["name"]] = np.array(inp["data"]).reshape(inp["shape"]).astype(dtype)

        results = self.session.run(None, inputs)
        outputs = []
        for i, meta in enumerate(self.session.get_outputs()):
            outputs.append({
                "name": meta.name,
                "shape": list(results[i].shape),
                "datatype": _numpy_dtype_to_kserve(results[i].dtype),
                "data": results[i].flatten().tolist(),
            })
        return {"model_name": self.name, "outputs": outputs}


DTYPE_MAP = {
    "FP32": np.float32, "FP16": np.float16, "FP64": np.float64,
    "INT8": np.int8, "INT16": np.int16, "INT32": np.int32, "INT64": np.int64,
    "UINT8": np.uint8, "UINT16": np.uint16, "UINT32": np.uint32, "UINT64": np.uint64,
    "BOOL": np.bool_,
}

NUMPY_TO_KSERVE = {v: k for k, v in DTYPE_MAP.items()}


def _kserve_dtype_to_numpy(dtype: str) -> np.dtype:
    return DTYPE_MAP.get(dtype, np.float32)


def _numpy_dtype_to_kserve(dtype: np.dtype) -> str:
    return NUMPY_TO_KSERVE.get(dtype.type, "FP32")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", default="/mnt/models")
    parser.add_argument("--http_port", type=int, default=8080)
    parser.add_argument("--grpc_port", type=int, default=8001)
    parser.add_argument("--providers", default="CPUExecutionProvider")
    args = parser.parse_args()

    providers = [p.strip() for p in args.providers.split(",")]
    model_name = os.environ.get("MODEL_NAME", "model")
    model = ONNXModel(model_name, args.model_path, providers)
    model.load()
    kserve.ModelServer(http_port=args.http_port).start([model])
