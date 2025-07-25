from pymongo import MongoClient
import pandas as pd
from datetime import datetime
import os

LOG_FILE = r"Logs/mongo_datafetch.xlsx"

def log_fetch_result(quote_id, status, reason_or_summary):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "Timestamp": timestamp,
        "Quote ID": str(quote_id),
        "Status": status,  # "Success" or "Failed"
        "Message": reason_or_summary
    }

    # Create or append log
    if os.path.exists(LOG_FILE):
        df = pd.read_excel(LOG_FILE)
    else:
        df = pd.DataFrame(columns=list(log_entry.keys()))

    df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
    df.to_excel(LOG_FILE, index=False)

# ----------------- MongoDB Fetch Function with Minimal Logging -----------------
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
        "quoteData.fba": 1,
        "quoteData.fbaOCC": 1,
        "quoteData.fbaDCC": 1
    }

    try:
        quote_doc = Quotes_collection.find_one({"_id": _id}, Quotes_projection)
        if not quote_doc:
            log_fetch_result(_id, "Failed", "Quote document not found in MongoDB.")
            return None, None

        entity_id = quote_doc.get("quoteSummary", {}).get("entityId")
        if not entity_id:
            log_fetch_result(_id, "Failed", "Missing entityId in quote document.")
            return None, None

        entity_doc = Entities_collection.find_one({"_id": entity_id}, {"entityName": 1})
        entity_name = entity_doc.get("entityName") if entity_doc else None

        result_summary = f"Origin: {quote_doc.get('quoteData', {}).get('origin', '')}; " \
                         f"Shipment Scope: {quote_doc.get('quoteSummary', {}).get('shipmentScope', '')}; " \
                         f"Entity: {entity_name or 'N/A'}"

        log_fetch_result(_id, "Success", result_summary)
        return quote_doc, entity_name

    except Exception as e:
        log_fetch_result(_id, "Failed", f"Exception: {str(e)}")
        return None, None
