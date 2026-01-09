# LLM Proxy (OpenAI-compatible → Ollama)

**Disclaimer:** This is a developer tool. It runs over plain HTTP by default (no TLS) and logs prompts/response previews to disk. Do not expose it to untrusted networks without adding HTTPS and tightening access controls.

Python FastAPI service that exposes a minimal OpenAI-compatible `/v1/chat/completions` endpoint and forwards to your private Ollama instances. API keys are configured statically, and adding new downstream models or clients is done via a single YAML file.

## Features
- OpenAI-style `/v1/chat/completions` (non-streaming) backed by Ollama `/api/chat`.
- Per-client API keys with model-level allow lists.
- Config-driven backends; add new Ollama endpoints without code changes.
- Logs every request/response preview to a host-mounted file.
- Docker + docker-compose for easy deployment; no external DB.

## Quick start
1. Edit `config/llm-proxy.yaml`:
   - Set your Ollama host in `backends[*].base_url` (e.g., `http://10.0.0.5:11434` or any reachable host/IP).
   - Add client API keys and allowed model mappings under `clients`. The OpenAI model name is what clients send; `backend` and `target_model` are internal routing.
2. Build and run:
   ```bash
   docker-compose build
   docker-compose up -d
   ```
3. Call the proxy (example):
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Authorization: Bearer sk-proxy-example" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gpt-4o",
       "messages": [{"role": "user", "content": "Hello from proxy"}]
     }'
    ```
   Or use the helper script:
   ```bash
   ./curl-test.sh
   # override defaults if needed:
   API_KEY=sk-your-key MODEL=gpt-4o PROMPT="hi" URL=http://localhost:8000/v1/chat/completions ./curl-test.sh
   ```

## Configuration
`config/llm-proxy.yaml` drives everything:
```yaml
server:
  host: 0.0.0.0
  port: 8000
logging:
  file: /var/log/llm-proxy/requests.log
  level: INFO
backends:
  - name: home-ollama
    base_url: http://ollama-box:11434
    timeout_seconds: 120
clients:
  - name: example-client
    api_key: sk-proxy-example
    allowed_models:
      - openai_model: gpt-4o      # model name clients send
        backend: home-ollama      # backend from the list above
        target_model: llama3      # Ollama model name
```
- **Add a new downstream Ollama**: append to `backends`.
- **Add a new client**: add to `clients` with a unique `api_key` and allowed model routes.
- Config is reloaded on-the-fly via file mtime; you can edit the YAML without restarting the container.

## Logging
- Requests and response previews are appended to `/var/log/llm-proxy/requests.log` (mounted to `./logs` via compose).
- API keys are not logged. Prompts and the first 200 chars of responses are logged for audit/debug.

## TLS / HTTPS
- The service itself is HTTP. If CrewAI Enterprise requires HTTPS, place an ingress/reverse-proxy (nginx/Traefik/Caddy) in front or terminate TLS at your provider; point it at the container’s port `8000`.

## Notes / limitations
- Only `/v1/chat/completions` is implemented; streaming and embeddings are not yet supported.
- Token usage is returned as zeros (Ollama does not expose counts directly).
- ZeroTier/VPN membership should be handled on the host; container just needs network reachability to your Ollama boxes.

## Development
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Health
- `GET /health` returns `{"status": "ok"}`.
- `GET /v1/models` returns the client’s allowed models.

## WARNING - Entirely Vibe Coded
