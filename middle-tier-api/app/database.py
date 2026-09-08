"""MongoDB connection and collection handles.

The middle tier talks to Mongo directly via a connection string (no HTTP layer),
per the system design notes.
"""

import os

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "SyllaSync_LocalDB")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

syllabi_collection = db["syllabi"]
tasks_collection = db["tasks"]


def ensure_indexes() -> None:
    """Create the indexes the app relies on. Safe to call repeatedly."""
    tasks_collection.create_index([("syllabusId", ASCENDING), ("dueAt", ASCENDING)])
    tasks_collection.create_index([("dueAt", ASCENDING)])
    syllabi_collection.create_index([("userId", ASCENDING), ("uploadedAt", ASCENDING)])
