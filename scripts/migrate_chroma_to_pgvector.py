#!/usr/bin/env python3
"""
Migrate vector data from Chroma to Pgvector.

Usage:
    python scripts/migrate_chroma_to_pgvector.py

Required environment variables:
    PGVECTOR_DB_URL     - PostgreSQL connection string (e.g. postgresql://user:pass@localhost/dbname)

Optional environment variables:
    CHROMA_DATA_PATH    - Path to Chroma's persistent storage (default: ./backend/data/vector_db)
    CHROMA_HTTP_HOST    - If using remote Chroma, set host (default: empty = local)
    CHROMA_HTTP_PORT    - Remote Chroma port (default: 8000)
    CHROMA_HTTP_SSL     - Use SSL for remote Chroma (default: false)
    CHROMA_TENANT       - Chroma tenant (default: default_tenant)
    CHROMA_DATABASE     - Chroma database (default: default_database)

    PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH - Max vector dimension (default: 1536)
    BATCH_SIZE          - Number of items per insert batch (default: 100)
    DRY_RUN             - Set to "true" to preview without writing (default: false)
"""

import os
import sys
import json
import logging
import argparse

import chromadb
from chromadb import Settings

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def get_chroma_client(args):
    """Initialize and return a Chroma client."""
    settings = Settings(allow_reset=False, anonymized_telemetry=False)
    http_host = args.chroma_http_host or os.environ.get("CHROMA_HTTP_HOST", "")
    tenant = os.environ.get("CHROMA_TENANT", chromadb.DEFAULT_TENANT)
    database = os.environ.get("CHROMA_DATABASE", chromadb.DEFAULT_DATABASE)

    if http_host:
        http_port = int(os.environ.get("CHROMA_HTTP_PORT", "8000"))
        http_ssl = os.environ.get("CHROMA_HTTP_SSL", "false").lower() == "true"
        log.info("Connecting to remote Chroma at %s:%d (ssl=%s)", http_host, http_port, http_ssl)
        return chromadb.HttpClient(
            host=http_host,
            port=http_port,
            ssl=http_ssl,
            tenant=tenant,
            database=database,
            settings=settings,
        )
    else:
        data_path = args.chroma_data_path or os.environ.get(
            "CHROMA_DATA_PATH", os.path.join("backend", "data", "vector_db")
        )
        log.info("Opening local Chroma at %s", data_path)
        return chromadb.PersistentClient(
            path=data_path,
            tenant=tenant,
            database=database,
            settings=settings,
        )


def get_pg_session(args):
    """Create a PostgreSQL session with pgvector extension."""
    pg_url = args.pgvector_db_url or os.environ.get("PGVECTOR_DB_URL")
    if not pg_url:
        log.error("PGVECTOR_DB_URL is required. Set it via --pgvector-db-url or env var.")
        sys.exit(1)
    if not pg_url.startswith("postgres"):
        log.error("PGVECTOR_DB_URL must be a PostgreSQL connection string.")
        sys.exit(1)

    engine = create_engine(pg_url, pool_pre_ping=True, poolclass=NullPool)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = scoped_session(session_factory)

    # Ensure pgvector extension exists
    session.execute(text("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                CREATE EXTENSION IF NOT EXISTS vector;
            END IF;
        END $$;
    """))
    session.commit()

    return session, engine


def ensure_table(session, vector_length):
    """Create the document_chunk table if it doesn't exist."""
    session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS document_chunk (
            id TEXT PRIMARY KEY,
            vector vector({vector_length}),
            collection_name TEXT NOT NULL,
            text TEXT,
            vmetadata JSONB
        );
    """))
    session.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_document_chunk_collection_name
        ON document_chunk (collection_name);
    """))
    session.commit()
    log.info("Ensured document_chunk table exists (vector dim=%d).", vector_length)


def list_collection_names(chroma_client):
    """Get collection names, handling both old (str) and new (Collection object) API."""
    collections = chroma_client.list_collections()
    if not collections:
        return []
    if isinstance(collections[0], str):
        return collections
    # Newer chromadb returns Collection objects
    return [c.name for c in collections]


def extract_from_chroma(chroma_client):
    """Extract all collections and their data (with embeddings) from Chroma."""
    collection_names = list_collection_names(chroma_client)
    log.info("Found %d collections in Chroma.", len(collection_names))

    all_data = {}
    for name in collection_names:
        collection = chroma_client.get_collection(name=name)
        result = collection.get(include=["embeddings", "documents", "metadatas"])

        ids = result.get("ids", [])
        embeddings = result.get("embeddings", [])
        documents = result.get("documents", [])
        metadatas = result.get("metadatas", [])

        if not ids:
            log.info("  Collection '%s': empty, skipping.", name)
            continue

        items = []
        for i, item_id in enumerate(ids):
            embedding = embeddings[i] if embeddings and i < len(embeddings) else None
            document = documents[i] if documents and i < len(documents) else None
            metadata = metadatas[i] if metadatas and i < len(metadatas) else None

            if embedding is None:
                log.warning("  Skipping item '%s' in '%s': no embedding.", item_id, name)
                continue

            items.append({
                "id": item_id,
                "vector": embedding,
                "text": document or "",
                "metadata": metadata or {},
            })

        all_data[name] = items
        log.info("  Collection '%s': %d items extracted.", name, len(items))

    return all_data


def adjust_vector(vector, target_length):
    """Pad or truncate a vector to the target length."""
    current = len(vector)
    if current < target_length:
        return vector + [0.0] * (target_length - current)
    elif current > target_length:
        return vector[:target_length]
    return vector


def load_into_pgvector(session, all_data, vector_length, batch_size, dry_run):
    """Insert extracted data into pgvector."""
    total_inserted = 0
    total_skipped = 0

    for collection_name, items in all_data.items():
        if dry_run:
            log.info("[DRY RUN] Would insert %d items into collection '%s'.",
                     len(items), collection_name)
            total_inserted += len(items)
            continue

        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            for item in batch:
                vector = adjust_vector(item["vector"], vector_length)
                metadata_json = json.dumps(item["metadata"]) if item["metadata"] else "{}"

                try:
                    session.execute(
                        text("""
                            INSERT INTO document_chunk (id, vector, collection_name, text, vmetadata)
                            VALUES (:id, :vector, :collection_name, :text, CAST(:metadata AS jsonb))
                            ON CONFLICT (id) DO UPDATE SET
                                vector = EXCLUDED.vector,
                                collection_name = EXCLUDED.collection_name,
                                text = EXCLUDED.text,
                                vmetadata = EXCLUDED.vmetadata
                        """),
                        {
                            "id": item["id"],
                            "vector": str(vector),
                            "collection_name": collection_name,
                            "text": item["text"],
                            "metadata": metadata_json,
                        },
                    )
                except Exception as e:
                    log.error("Failed to insert item '%s' in '%s': %s",
                              item["id"], collection_name, e)
                    session.rollback()
                    total_skipped += 1
                    continue

            session.commit()
            total_inserted += len(batch)
            log.info("  Collection '%s': inserted batch %d-%d / %d.",
                     collection_name, i + 1, min(i + batch_size, len(items)), len(items))

    return total_inserted, total_skipped


def verify_migration(chroma_client, session):
    """Compare collection counts between Chroma and pgvector."""
    log.info("--- Verification ---")
    collection_names = list_collection_names(chroma_client)
    all_match = True

    for name in collection_names:
        collection = chroma_client.get_collection(name=name)
        chroma_count = collection.count()

        result = session.execute(
            text("SELECT COUNT(*) FROM document_chunk WHERE collection_name = :name"),
            {"name": name},
        )
        pg_count = result.scalar()

        status = "OK" if chroma_count == pg_count else "MISMATCH"
        if status == "MISMATCH":
            all_match = False
        log.info("  %-50s  Chroma: %5d  Pgvector: %5d  [%s]",
                 name, chroma_count, pg_count, status)

    if all_match:
        log.info("All collections migrated successfully.")
    else:
        log.warning("Some collections have mismatched counts. Review the output above.")

    return all_match


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Open WebUI vector data from Chroma to Pgvector.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--pgvector-db-url",
        help="PostgreSQL connection string (or set PGVECTOR_DB_URL env var)",
    )
    parser.add_argument(
        "--chroma-data-path",
        help="Path to local Chroma data (or set CHROMA_DATA_PATH env var)",
    )
    parser.add_argument(
        "--chroma-http-host",
        help="Remote Chroma host (or set CHROMA_HTTP_HOST env var)",
    )
    parser.add_argument(
        "--vector-length",
        type=int,
        default=int(os.environ.get("PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH", "1536")),
        help="Vector dimension length (default: 1536)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("BATCH_SIZE", "100")),
        help="Rows per insert batch (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN", "false").lower() == "true",
        help="Preview migration without writing to pgvector",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip post-migration verification",
    )
    args = parser.parse_args()

    log.info("=== Chroma -> Pgvector Migration ===")
    if args.dry_run:
        log.info("DRY RUN mode enabled. No data will be written.")

    # 1. Connect to Chroma
    chroma_client = get_chroma_client(args)

    # 2. Connect to PostgreSQL
    if not args.dry_run:
        session, engine = get_pg_session(args)
        ensure_table(session, args.vector_length)
    else:
        session, engine = None, None

    # 3. Extract all data from Chroma
    log.info("--- Extracting from Chroma ---")
    all_data = extract_from_chroma(chroma_client)

    if not all_data:
        log.info("No data found in Chroma. Nothing to migrate.")
        return

    # Check vector dimensions
    sample_collection = next(iter(all_data.values()))
    if sample_collection:
        sample_dim = len(sample_collection[0]["vector"])
        if sample_dim != args.vector_length:
            log.warning(
                "Detected vector dimension %d but --vector-length is %d. "
                "Vectors will be padded/truncated. Consider setting "
                "--vector-length=%d to match your embedding model.",
                sample_dim, args.vector_length, sample_dim,
            )

    total_items = sum(len(items) for items in all_data.values())
    log.info("Total items to migrate: %d across %d collections.", total_items, len(all_data))

    # 4. Load into pgvector
    log.info("--- Loading into Pgvector ---")
    inserted, skipped = load_into_pgvector(
        session, all_data, args.vector_length, args.batch_size, args.dry_run
    )
    log.info("Inserted: %d, Skipped: %d", inserted, skipped)

    # 5. Verify
    if not args.dry_run and not args.skip_verify:
        verify_migration(chroma_client, session)

    if session:
        session.remove()

    log.info("=== Migration complete ===")
    if not args.dry_run:
        log.info(
            "Next steps:\n"
            "  1. Set VECTOR_DB=pgvector in your environment\n"
            "  2. Set PGVECTOR_DB_URL to your PostgreSQL connection string\n"
            "  3. Set PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH=%d\n"
            "  4. Restart Open WebUI",
            args.vector_length,
        )


if __name__ == "__main__":
    main()
