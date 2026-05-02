# mycelium-embeddings

Tiny shared library: text → 1536-dim float vector.

## Why this exists

Three places need embeddings: the event embedder in `services/knowledge`, the
agent memory writer in `services/agent-runtime`, and the future code-index
chunker. Pulling them through one `EmbeddingProvider` interface means we can:

- swap providers (OpenAI ↔ local model ↔ hash) via one env var,
- keep a deterministic offline mode for dev/CI,
- keep `EMBEDDING_DIM = 1536` consistent with the Postgres `vector(1536)`
  columns and IVFFlat indexes defined in `packages/db`.

## Selecting a provider

```bash
EMBEDDING_PROVIDER=hash    # default; deterministic, no network
EMBEDDING_PROVIDER=openai  # text-embedding-3-small; needs OPENAI_API_KEY
```

If `openai` is selected but the API key is missing, the factory logs a
warning and falls back to `hash`. This keeps `docker compose up` working
without secrets while still respecting the production setting.

## Public surface

```python
from mycelium_embeddings import get_default_provider, EMBEDDING_DIM

provider = get_default_provider()
vec = await provider.embed("hello world")
batch = await provider.embed_many(["a", "b", "c"])
```
