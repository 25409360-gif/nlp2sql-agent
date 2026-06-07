import hashlib
import math
import re
import time
from collections.abc import Sequence

from app.core.config import settings


class EmbeddingClientError(RuntimeError):
    pass


class EmbeddingTimeoutError(EmbeddingClientError):
    pass


class EmbeddingDimensionError(EmbeddingClientError):
    pass


class EmbeddingClient:
    def __init__(
        self,
        model: str | None = None,
        dimension: int | None = None,
        batch_size: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.model = model or settings.embedding_model
        self.dimension = dimension if dimension is not None else settings.embedding_dimension
        self.batch_size = batch_size if batch_size is not None else settings.embedding_batch_size
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.embedding_timeout_seconds
        )

        if self.dimension <= 0:
            raise EmbeddingDimensionError("embedding dimension must be greater than 0")
        if self.batch_size <= 0:
            raise EmbeddingClientError("embedding batch size must be greater than 0")
        if self.timeout_seconds <= 0:
            raise EmbeddingClientError("embedding timeout must be greater than 0")

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        started_at = time.monotonic()
        vectors: list[list[float]] = []

        for batch_start in range(0, len(texts), self.batch_size):
            self._raise_if_timeout(started_at)
            batch = texts[batch_start : batch_start + self.batch_size]
            batch_vectors = self._embed_batch(batch)
            self._raise_if_timeout(started_at)
            for vector in batch_vectors:
                self._validate_vector(vector)
            vectors.extend(batch_vectors)

        return vectors

    def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError

    def _raise_if_timeout(self, started_at: float) -> None:
        if time.monotonic() - started_at > self.timeout_seconds:
            raise EmbeddingTimeoutError("embedding generation timed out")

    def _validate_vector(self, vector: Sequence[float]) -> None:
        if len(vector) != self.dimension:
            raise EmbeddingDimensionError(
                f"expected embedding dimension {self.dimension}, got {len(vector)}"
            )
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingDimensionError("embedding vector contains non-finite values")


class LocalHashEmbeddingClient(EmbeddingClient):
    _token_pattern = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]|[^\s]", re.IGNORECASE)

    def _embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokenize(text)

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 12) * 0.05
            vector[index] += sign * weight

        return self._normalize(vector)

    def _tokenize(self, text: str) -> list[str]:
        tokens = self._token_pattern.findall(text.lower())
        if not tokens:
            return ["<empty>"]

        bigrams = [f"{tokens[index]}{tokens[index + 1]}" for index in range(len(tokens) - 1)]
        return tokens + bigrams

    def _normalize(self, vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def create_embedding_client() -> EmbeddingClient:
    if settings.embedding_provider == "local":
        return LocalHashEmbeddingClient()

    raise EmbeddingClientError(f"Unsupported embedding provider: {settings.embedding_provider}")
