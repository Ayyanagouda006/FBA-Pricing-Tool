from pymongo import MongoClient

# ----------------- MongoDB Fetch Function -----------------
def fetch_quote_data(_id):
    host = "65.1.22.99"
    port = "27017"
    database_name = "agdb-prod2"

    client = MongoClient(f'mongodb://{host}:{port}/')
    db = client[database_name]

    Quotes_collection = db["Quotes"]
    Entities_collection = db["SHEntities"]

    Quotes_projection = {
        "quoteSummary.entityId": 1,
        "quoteSummary.shipmentScope": 1,
        "quoteData.origin": 1,
        "quoteData.multidest": 1,
        "quoteData.cargoReadinessDate": 1,
        "quoteData.fba":1,
        "quoteData.fbaOCC":1,
        "quoteData.fbaDCC":1
    }

    quote_doc = Quotes_collection.find_one({"_id": _id}, Quotes_projection)
    if not quote_doc:
        return None, None

    entity_id = quote_doc.get("quoteSummary", {}).get("entityId")
    entity_name = None
    if entity_id:
        entity_doc = Entities_collection.find_one({"_id": entity_id}, {"entityName": 1})
        if entity_doc:
            entity_name = entity_doc.get("entityName")

    return quote_doc, entity_name