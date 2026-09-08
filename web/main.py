import os
import json
import datetime
import ssl

import jwt
import httpx
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from kubernetes import client, config

app = FastAPI()

PASSWORD = os.getenv("COMMAND_PASSWORD", "commander")
JWT_SECRET = os.getenv("JWT_SECRET", os.urandom(32).hex())
NAMESPACE = os.getenv("NAMESPACE", "john")

try:
    config.load_incluster_config()
except Exception:
    config.load_kube_config()

custom_api = client.CustomObjectsApi()


class LoginRequest(BaseModel):
    password: str


def verify_token(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/api/auth/login")
def login(req: LoginRequest):
    if req.password != PASSWORD:
        raise HTTPException(status_code=401, detail="Access denied")
    token = jwt.encode(
        {"sub": "commander", "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"token": token}


@app.get("/api/models", dependencies=[Depends(verify_token)])
def list_models():
    isvcs = custom_api.list_namespaced_custom_object(
        group="serving.kserve.io",
        version="v1beta1",
        namespace=NAMESPACE,
        plural="inferenceservices",
    )
    models = []
    for isvc in isvcs.get("items", []):
        name = isvc["metadata"]["name"]
        annotations = isvc.get("metadata", {}).get("annotations", {})
        display = annotations.get("openshift.io/display-name", name)
        description = annotations.get("openshift.io/description", "")
        conditions = isvc.get("status", {}).get("conditions", [])
        ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
        url = isvc.get("status", {}).get("address", {}).get("url", "")
        models.append({"name": name, "display": display, "description": description, "ready": ready, "url": url})
    return {"models": models}


def _get_model_url(model_name: str) -> str:
    isvc = custom_api.get_namespaced_custom_object(
        group="serving.kserve.io",
        version="v1beta1",
        namespace=NAMESPACE,
        plural="inferenceservices",
        name=model_name,
    )
    url = isvc.get("status", {}).get("address", {}).get("url", "")
    if not url:
        raise HTTPException(status_code=502, detail=f"Model {model_name} has no endpoint")
    return url


def _get_sa_token() -> str | None:
    path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return None


@app.post("/api/chat/completions", dependencies=[Depends(verify_token)])
async def chat_completions(request: Request):
    body = await request.json()
    model_endpoint = body.pop("model_endpoint", None)
    if not model_endpoint:
        raise HTTPException(status_code=400, detail="model_endpoint required")

    base_url = _get_model_url(model_endpoint)
    body.setdefault("model", "default")
    stream = body.get("stream", False)

    headers = {"Content-Type": "application/json"}
    sa_token = _get_sa_token()
    if sa_token:
        headers["Authorization"] = f"Bearer {sa_token}"

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    timeout = httpx.Timeout(connect=60.0, read=300.0, write=30.0, pool=30.0)

    if stream:
        async def generate():
            try:
                async with httpx.AsyncClient(verify=ssl_ctx, timeout=timeout) as c:
                    async with c.stream("POST", f"{base_url}/v1/chat/completions", json=body, headers=headers) as resp:
                        if resp.status_code != 200:
                            error_text = (await resp.aread()).decode("utf-8", errors="replace")
                            yield f"data: {json.dumps({'error': {'message': error_text, 'code': resp.status_code}})}\n\ndata: [DONE]\n\n"
                            return
                        async for chunk in resp.aiter_text():
                            yield chunk
            except httpx.TimeoutException:
                yield f"data: {json.dumps({'error': {'message': 'upstream timeout', 'code': 504}})}\n\ndata: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': {'message': str(e), 'code': 502}})}\n\ndata: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    async with httpx.AsyncClient(verify=ssl_ctx, timeout=timeout) as c:
        resp = await c.post(f"{base_url}/v1/chat/completions", json=body, headers=headers)
        return resp.json()


app.mount("/", StaticFiles(directory="static", html=True), name="static")
