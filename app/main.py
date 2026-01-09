import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import ConfigLoader, resolve_logging_path
from .ollama_client import OllamaClient


CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config/llm-proxy.yaml")
config_loader = ConfigLoader(CONFIG_PATH)

# Initialize logging before app creation so early errors are captured.
try:
    log_path = resolve_logging_path(config_loader.load())
except Exception:
    # Fall back to a default path if config isn't ready yet.
    log_path = "/var/log/llm-proxy/requests.log"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    filename=log_path,
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("llm-proxy")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = Field(default=None)
    max_tokens: Optional[int] = Field(default=None, alias="max_tokens")


def load_backend(config: Dict[str, Any], name: str) -> Dict[str, Any]:
    for backend in config.get("backends", []):
        if backend.get("name") == name:
            return backend
    raise HTTPException(status_code=400, detail=f"Backend '{name}' not found")


def resolve_client(config: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    for client in config.get("clients", []):
        if client.get("api_key") == api_key:
            return client
    raise HTTPException(status_code=401, detail="Invalid API key")


def resolve_route(client: Dict[str, Any], requested_model: str) -> Dict[str, str]:
    for mapping in client.get("allowed_models", []):
        if mapping.get("openai_model") == requested_model:
            return {
                "backend_name": mapping["backend"],
                "target_model": mapping.get("target_model", requested_model),
            }
    raise HTTPException(
        status_code=400,
        detail=f"Model '{requested_model}' not allowed for this client",
    )


def build_openai_like_response(
    model: str, content: str, prompt: List[Dict[str, Any]]
) -> Dict[str, Any]:
    created = int(time.time())
    response_id = f"chatcmpl-{uuid.uuid4().hex}"
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


async def get_config() -> Dict[str, Any]:
    return config_loader.load()


async def authenticate(
    request: Request, config: Dict[str, Any] = Depends(get_config)
) -> Dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    client = resolve_client(config, token)
    return client


app = FastAPI(title="OpenAI-compatible Ollama proxy")


@app.exception_handler(httpx.HTTPStatusError)  # type: ignore[name-defined]
async def httpx_error_handler(
    request: Request, exc: Any
) -> JSONResponse:  # pragma: no cover
    logger.error("Downstream HTTP error: %s", exc)
    return JSONResponse(
        status_code=502,
        content={"error": {"message": "Downstream Ollama error", "type": "server_error"}},
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    req: ChatCompletionRequest,
    request: Request,
    config: Dict[str, Any] = Depends(get_config),
    client: Dict[str, Any] = Depends(authenticate),
):
    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming not supported yet")

    route = resolve_route(client, req.model)
    backend_cfg = load_backend(config, route["backend_name"])
    ollama = OllamaClient(
        base_url=backend_cfg["base_url"],
        timeout=backend_cfg.get("timeout_seconds", 120),
    )

    # Prepare messages for Ollama.
    upstream_messages = [{"role": m.role, "content": m.content} for m in req.messages]
    logger.info(
        "request client=%s model=%s backend=%s target_model=%s prompt=%s",
        client.get("name"),
        req.model,
        route["backend_name"],
        route["target_model"],
        upstream_messages,
    )

    upstream_resp = await ollama.chat(
        model=route["target_model"], messages=upstream_messages
    )
    content = upstream_resp.get("message", {}).get("content", "")

    resp = build_openai_like_response(req.model, content, upstream_messages)
    logger.info(
        "response client=%s model=%s backend=%s target_model=%s content_preview=%s",
        client.get("name"),
        req.model,
        route["backend_name"],
        route["target_model"],
        content[:200],
    )
    return resp


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models(
    config: Dict[str, Any] = Depends(get_config),
    client: Dict[str, Any] = Depends(authenticate),
) -> Dict[str, Any]:
    models = [
        {"id": m["openai_model"], "object": "model"}
        for m in client.get("allowed_models", [])
    ]
    return {"object": "list", "data": models}
