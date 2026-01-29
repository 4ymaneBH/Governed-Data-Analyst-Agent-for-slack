import os
import httpx
import structlog
from typing import List, Optional

logger = structlog.get_logger()

class EmbeddingService:
    """Service to generate embeddings using Ollama."""
    
    def __init__(self, base_url: str = None, model: str = "nomic-embed-text"):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
        self.model = model
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text string."""
        try:
            response = await self.client.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                }
            )
            response.raise_for_status()
            return response.json()["embedding"]
            
        except httpx.HTTPError as e:
            logger.error("Embedding generation failed", error=str(e), model=self.model)
            # Return zero vector or raise depending on policy
            raise RuntimeError(f"Failed to generate embedding: {str(e)}")

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        embeddings = []
        for text in texts:
            # Ollama currently doesn't support batch embeddings natively in the API consistently
            # across all versions, so we loop. Optimizable later.
            try:
                emb = await self.generate_embedding(text)
                embeddings.append(emb)
            except Exception as e:
                logger.error("Batch embedding failure", error=str(e), text_sample=text[:50])
                embeddings.append([]) # Append empty on fail to keep index alignment? Or fail?
                # For now, let's just re-raise as reliable indexing is crucial
                raise e
        return embeddings

    async def close(self):
        await self.client.aclose()
