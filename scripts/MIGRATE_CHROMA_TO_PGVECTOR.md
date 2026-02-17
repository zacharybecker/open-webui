# Migrating from Chroma to Pgvector

This guide walks through migrating your Open WebUI vector database from the default Chroma backend to PostgreSQL with pgvector.

## Prerequisites

- A running PostgreSQL instance (v15+ recommended) with the [pgvector extension](https://github.com/pgvector/pgvector) installed
- Access to your existing Chroma data (local directory or remote HTTP)
- Python dependencies already installed from Open WebUI (`chromadb`, `sqlalchemy`, `pgvector`)

## Quick Start

```bash
# 1. Preview what will be migrated (no writes)
python scripts/migrate_chroma_to_pgvector.py \
  --pgvector-db-url "postgresql://user:pass@localhost/openwebui" \
  --dry-run

# 2. Run the actual migration
python scripts/migrate_chroma_to_pgvector.py \
  --pgvector-db-url "postgresql://user:pass@localhost/openwebui"

# 3. Update your Open WebUI config and restart
export VECTOR_DB=pgvector
export PGVECTOR_DB_URL="postgresql://user:pass@localhost/openwebui"
```

## CLI Options

| Flag | Env Var | Default | Description |
|------|---------|---------|-------------|
| `--pgvector-db-url` | `PGVECTOR_DB_URL` | *(required)* | PostgreSQL connection string |
| `--chroma-data-path` | `CHROMA_DATA_PATH` | `backend/data/vector_db` | Path to local Chroma storage |
| `--chroma-http-host` | `CHROMA_HTTP_HOST` | *(empty = local)* | Remote Chroma host |
| `--vector-length` | `PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH` | `1536` | Embedding dimension |
| `--batch-size` | `BATCH_SIZE` | `100` | Rows per insert batch |
| `--dry-run` | `DRY_RUN=true` | `false` | Preview without writing |
| `--skip-verify` | — | `false` | Skip post-migration count check |

## Examples

### Local Chroma (default setup)

```bash
python scripts/migrate_chroma_to_pgvector.py \
  --pgvector-db-url "postgresql://user:pass@localhost/openwebui" \
  --chroma-data-path ./backend/data/vector_db
```

### Remote Chroma

```bash
CHROMA_HTTP_HOST=chroma.example.com \
CHROMA_HTTP_PORT=8000 \
python scripts/migrate_chroma_to_pgvector.py \
  --pgvector-db-url "postgresql://user:pass@localhost/openwebui"
```

### Custom embedding dimension

If your embedding model produces vectors other than 1536 dimensions (e.g. 768 for `nomic-embed-text`), specify the correct length:

```bash
python scripts/migrate_chroma_to_pgvector.py \
  --pgvector-db-url "postgresql://user:pass@localhost/openwebui" \
  --vector-length 768
```

The script will auto-detect your actual vector dimensions and warn you if they don't match.

## What the Script Does

1. **Connects to Chroma** and enumerates all collections
2. **Extracts** every item including embeddings, document text, and metadata
3. **Creates** the `document_chunk` table and indexes in PostgreSQL (if they don't exist)
4. **Upserts** all data in batches — safe to re-run without duplicating data
5. **Verifies** by comparing per-collection item counts between Chroma and pgvector

## Post-Migration Configuration

After a successful migration, update your Open WebUI environment:

```bash
# Required
VECTOR_DB=pgvector
PGVECTOR_DB_URL=postgresql://user:pass@localhost/openwebui

# Match your embedding model's dimension
PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH=1536

# Optional tuning
PGVECTOR_INDEX_METHOD=hnsw          # or ivfflat (default)
PGVECTOR_HNSW_M=16                  # HNSW max connections
PGVECTOR_HNSW_EF_CONSTRUCTION=64    # HNSW construction quality
PGVECTOR_POOL_SIZE=5                # connection pool size
```

Then restart Open WebUI.

## Troubleshooting

### "PGVECTOR_DB_URL must be a PostgreSQL connection string"

The connection string must start with `postgresql://` or `postgres://`.

### Vector dimension mismatch

If the script warns about dimension mismatch, the `--vector-length` flag doesn't match your actual embeddings. Set it to match your embedding model's output dimension (e.g. 1536 for OpenAI `text-embedding-ada-002`, 768 for `nomic-embed-text`).

### Permission denied creating the vector extension

If your PostgreSQL user can't create extensions, ask your DBA to run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Then re-run the migration. You can also set `PGVECTOR_CREATE_EXTENSION=false` in Open WebUI's config to skip the automatic extension creation on startup.

### Partial migration / interrupted run

The script uses `ON CONFLICT ... DO UPDATE`, so it's safe to re-run. Just execute the same command again and it will pick up where it left off (overwriting any previously inserted rows).
