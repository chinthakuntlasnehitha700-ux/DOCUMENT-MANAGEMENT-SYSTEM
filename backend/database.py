
import os
from datetime import datetime, timezone

from pymongo import MongoClient, ReturnDocument, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing from environment variables.")

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=10000
)

db = client["documind_ai"]

documents_collection = db["documents"]
counters_collection = db["counters"]


def create_tables():
    """Connect to MongoDB and prepare collections."""

    client.admin.command("ping")

    documents_collection.create_index(
        [("id", ASCENDING)],
        unique=True
    )

    documents_collection.create_index(
        [("uploaded_at", DESCENDING)]
    )

    print("MongoDB Connected Successfully!")

    migrate_old_documents()


def next_document_id():
    """Generate an integer ID for the website."""

    counter = counters_collection.find_one_and_update(
        {"_id": "documents"},
        {"$inc": {"sequence_value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    return counter["sequence_value"]


def migrate_old_documents():
    """
    Copy existing PostgreSQL documents into MongoDB.
    Existing document IDs are preserved.
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("No old PostgreSQL database configured. Migration skipped.")
        return

    try:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(
            database_url,
            row_factory=dict_row,
            connect_timeout=10
        )

        try:
            old_documents = connection.execute("""
                SELECT id, filename, stored_name, file_type,
                       category, extracted_text, uploaded_at
                FROM documents
            """).fetchall()
        finally:
            connection.close()

        migrated_count = 0
        highest_id = 0

        for old_document in old_documents:
            document = dict(old_document)

            document_id = int(document["id"])
            highest_id = max(highest_id, document_id)

            document["id"] = document_id

            if document.get("uploaded_at") is None:
                document["uploaded_at"] = datetime.now(timezone.utc)

            existing = documents_collection.find_one(
                {"id": document_id}
            )

            if existing is None:
                documents_collection.insert_one(document)
                migrated_count += 1

        if highest_id:
            counters_collection.update_one(
                {"_id": "documents"},
                {
                    "$max": {
                        "sequence_value": highest_id
                    }
                },
                upsert=True
            )

        print(
            f"MongoDB migration completed. "
            f"{migrated_count} old documents copied."
        )

    except Exception as error:
        print("OLD DATABASE MIGRATION ERROR:", str(error))
        raise


def get_documents_collection():
    return documents_collection
