import asyncio
import os
import sys
import asyncpg
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.mcp_server.embeddings import EmbeddingService

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analyst:analyst_secret@localhost:5432/analyst_db")

async def backfill():
    print(f"Connecting to database: {DATABASE_URL}")
    pool = await asyncpg.create_pool(DATABASE_URL)
    
    # Initialize embedding service
    # For local script, might need to point to localhost if ollama is running locally
    # or container name if running in docker network.
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    
    print(f"Initializing EmbeddingService with URL: {ollama_url}, Model: {model}")
    embedder = EmbeddingService(base_url=ollama_url, model=model)
    
    try:
        async with pool.acquire() as conn:
            # Get chunks without embeddings
            rows = await conn.fetch("""
                SELECT chunk_id, content 
                FROM internal.doc_chunks 
                WHERE embedding IS NULL
            """)
            
            print(f"Found {len(rows)} chunks to backfill...")
            
            count = 0
            for row in rows:
                chunk_id = row["chunk_id"]
                content = row["content"]
                
                try:
                    embedding = await embedder.generate_embedding(content)
                    
                    # Update DB
                    # Format embedding as string for postgres vector
                    # Or use a list depending on driver support. asyncpg usually takes string for vector or list?
                    # pgvector-python recommends list if register_vector is used, but here we might need string literal
                    # Let's try string literal format "[0.1,0.2,...]"
                    embedding_str = f"[{','.join(map(str, embedding))}]"
                    
                    await conn.execute("""
                        UPDATE internal.doc_chunks 
                        SET embedding = $1 
                        WHERE chunk_id = $2
                    """, embedding_str, chunk_id)
                    
                    count += 1
                    if count % 10 == 0:
                        print(f"Processed {count}/{len(rows)} chunks")
                        
                except Exception as e:
                    print(f"Failed to process chunk {chunk_id}: {e}")
                    
            print(f"Backfill complete! Updated {count} chunks.")
            
    finally:
        await embedder.close()
        await pool.close()

if __name__ == "__main__":
    asyncio.run(backfill())
