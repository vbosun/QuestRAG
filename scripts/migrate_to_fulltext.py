"""Migrate Milvus collection to a new one with full-text search enabled.

Usage:
    python scripts/migrate_to_fulltext.py [--drop-old]

After migration:
    1. Update MILVUS_COLLECTION_NAME in .env to the new collection name
    2. Or run with --drop-old to drop old collection and recreate with old name
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")
MILVUS_COLLECTION_NAME = os.environ.get("MILVUS_COLLECTION_NAME", "questrag_chunks")


def main():
    parser = argparse.ArgumentParser(description="Migrate Milvus collection to full-text search")
    parser.add_argument(
        "--target-name",
        default=None,
        help="Target collection name (default: <source>_v2)",
    )
    parser.add_argument(
        "--drop-old",
        action="store_true",
        help="Drop old collection after migration",
    )
    args = parser.parse_args()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

    from quest_rag.rag.vector_backend import MilvusVectorBackend

    backend = MilvusVectorBackend(
        host=MILVUS_HOST,
        port=MILVUS_PORT,
        collection_name=MILVUS_COLLECTION_NAME,
    )

    # Pre-flight: check text field
    desc = backend._mc.describe_collection(MILVUS_COLLECTION_NAME)
    text_field = next((f for f in desc["fields"] if f["name"] == "text"), None)
    if text_field and text_field.get("enable_analyzer"):
        print(f"Collection '{MILVUS_COLLECTION_NAME}' already has full-text search enabled.")
        return

    target_name = args.target_name or f"{MILVUS_COLLECTION_NAME}_v2"

    print(f"Migrating '{MILVUS_COLLECTION_NAME}' -> '{target_name}'")
    print(f"Milvus: {MILVUS_HOST}:{MILVUS_PORT}")
    print()

    result = backend.migrate_to_fulltext(target_name=target_name)

    print()
    print(f"Source: {result['source']}  ({result['source_rows']} rows)")
    print(f"Target: {result['target']}  ({result['target_rows']} rows)")

    if result["source_rows"] != result["target_rows"]:
        print(f"WARNING: row count mismatch! ({result['source_rows']} vs {result['target_rows']})")
        return

    print("Migration complete.")
    print()

    if args.drop_old:
        print(f"Dropping old collection '{MILVUS_COLLECTION_NAME}' ...")
        backend._mc.drop_collection(MILVUS_COLLECTION_NAME)
        print("Done.")
        print(f"Update .env: MILVUS_COLLECTION_NAME={target_name}")
    else:
        print("Next steps:")
        print(f"  1. Verify the new collection: check data in '{target_name}'")
        print(f"  2. Update .env: MILVUS_COLLECTION_NAME={target_name}")
        print(f"  3. Or run with --drop-old to auto-drop old collection")


if __name__ == "__main__":
    main()
