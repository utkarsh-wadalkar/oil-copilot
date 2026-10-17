"""Local CPU MiniLM embeddings.

The model is imported lazily so the API and worker stay importable when the
optional ``sentence-transformers`` dependency or its model files are absent. A
missing dependency is reported truthfully through :meth:`LocalEmbedder.status`
rather than silently returning fabricated vectors.
"""
from __future__ import annotations

from app.config import Settings, get_settings


class EmbeddingsUnavailable(RuntimeError):
    """Raised when the local embedding model cannot be loaded."""


class LocalEmbedder:
    """CPU-only all-MiniLM-L6-v2 embedder with tokenizer-length enforcement."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.model_name = self.settings.embeddings_model
        self.max_tokens = int(self.settings.embeddings_max_tokens)
        self._model = None
        self._tokenizer = None
        self._load_error: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def _ensure_loaded(self):
        if self._model is not None:
            return
        if self._load_error is not None:
            raise EmbeddingsUnavailable(self._load_error)
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover - depends on optional install
            self._load_error = f'sentence-transformers unavailable: {type(exc).__name__}'
            raise EmbeddingsUnavailable(self._load_error) from exc
        try:
            model = SentenceTransformer(self.model_name, device='cpu')
            # MiniLM accepts 256 tokens; bound the context so long chunks cannot
            # silently truncate inside the transformer.
            try:
                model.max_seq_length = self.max_tokens
            except Exception:
                pass
            self._model = model
            self._tokenizer = getattr(model, 'tokenizer', None)
        except Exception as exc:  # pragma: no cover - model download/integrity
            self._load_error = f'embedding model load failed: {type(exc).__name__}: {exc}'
            raise EmbeddingsUnavailable(self._load_error) from exc

    def status(self) -> dict:
        base = {'available': self._model is not None, 'model': self.model_name,
                'dimensions': self.settings.mem0_embedding_dims}
        if self._load_error and self._model is None:
            base['available'] = False
            base['reason'] = self._load_error
        return base

    # -- embedding ---------------------------------------------------------
    def _truncate(self, text: str) -> str:
        if self._tokenizer is None:
            return text
        try:
            ids = self._tokenizer.encode(text, add_special_tokens=True, truncation=True,
                                         max_length=self.max_tokens)
            return self._tokenizer.decode(ids, skip_special_tokens=True)
        except Exception:
            # Fall back to a conservative character bound (~4 chars/token).
            return text[: self.max_tokens * 4]

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        prepared = [self._truncate(t or '') for t in texts]
        vectors = self._model.encode(prepared, normalize_embeddings=True, convert_to_numpy=True)
        return [list(map(float, vector)) for vector in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
