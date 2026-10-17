"""Ollama Cloud chat provider (native /api/chat with server-side credentials)."""
from __future__ import annotations

import httpx

from app.config import Settings, get_settings


class ProviderError(RuntimeError):
    pass


class ProviderRateLimited(ProviderError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailable(ProviderError):
    pass


class OllamaProvider:
    """Thin, injectable client over Ollama's native chat API."""

    def __init__(self, settings: Settings | None = None, client=None):
        self.settings = settings or get_settings()
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.settings.ollama_api_key)

    def _http(self):
        if self._client is not None:
            return self._client
        self._client = httpx.Client(base_url=self.settings.ollama_base_url.rstrip('/'),
                                    timeout=httpx.Timeout(120.0, connect=15.0))
        return self._client

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None) -> dict:
        if not self.configured:
            raise ProviderUnavailable('no model credentials configured')
        payload = {'model': model or self.settings.ollama_model, 'messages': messages, 'stream': False}
        if tools:
            payload['tools'] = tools
        try:
            response = self._http().post('/api/chat', json=payload,
                                         headers={'Authorization': f'Bearer {self.settings.ollama_api_key}'})
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f'{type(exc).__name__}: {exc}') from exc
        if response.status_code == 429:
            retry_after = response.headers.get('retry-after')
            raise ProviderRateLimited('model rate limited', float(retry_after) if retry_after else None)
        if response.status_code >= 400:
            raise ProviderError(f'model error HTTP {response.status_code}')
        data = response.json()
        return data.get('message') or {}

    def status(self) -> dict:
        return {'configured': self.configured, 'model': self.settings.ollama_model,
                'base_url': self.settings.ollama_base_url}
