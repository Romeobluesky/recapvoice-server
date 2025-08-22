import os
import json
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "packetwave"

def apply_schemas(schema_dir):
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    print(f"Connected to MongoDB: {MONGO_URI}, Database: {DB_NAME}")

    for file_name in os.listdir(schema_dir):
        if file_name.endswith(".json"):
            collection_name = file_name.replace("_schema.json", "")
            file_path = os.path.join(schema_dir, file_name)

            with open(file_path, "r") as file:
                data = json.load(file)
                collection = db[collection_name]
                collection.insert_many(data)
                print(f"Initialized collection: {collection_name}")

    print("Schema initialization complete.")
    client.close()

if __name__ == "__main__":
    schema_directory = os.path.join("workspace", "program", "schemas")
    apply_schemas(schema_directory)
