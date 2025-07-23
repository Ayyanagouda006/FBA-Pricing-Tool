import requests
import pandas as pd
from datetime import datetime, timedelta

def get_jbhunt_quote_df(origin_zip, destination_zip, weight_lbs):

    
    # === Step 1: Get Access Token ===
    auth_url = "https://sso.jbhunt.com/auth/realms/security360/protocol/openid-connect/token"

    auth_payload = {
        "grant_type": "client_credentials",
        "client_id": "agraga-client",
        "client_secret": "ilxIBoKVY8tq62IrFzO1GWR5NEy3BCgw"
    }
    auth_headers = {"Content-Type": "application/x-www-form-urlencoded"}

    auth_response = requests.post(auth_url, data=auth_payload, headers=auth_headers)
    auth_response.raise_for_status()
    access_token = auth_response.json()["access_token"]

    # === Step 2: Prepare Dynamic Quote Payload ===
    quote_url = "https://api.jbhunt.com/pricing/quoting/v3/dynamic-quote"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Api-Key": "numkVeNBUgFGQPo0xA2VBWfk8Anss4iJqc9GMdYO7Lo8sOZG",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Use pickup date as tomorrow (UTC)
    pickup_date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT12:00:00Z")

    payload = {
        "origin": {
            "postalCode": str(origin_zip).zfill(5),
            "countryCode": "USA"
        },
        "destination": {
            "postalCode": str(destination_zip).zfill(5),
            "countryCode": "USA"
        },
        "pickupDateTime": pickup_date,
        "billToCode": "TABRCO",  # Replace if needed
        "shipmentId": "",
        "options": {
            "totalWeightInPounds": weight_lbs,
            "equipmentType": "DryVan",
            "containsHazardousMaterial": False,
            "isIntermodalLoad": None,
            "isLiveLoad": None,
            "scacCode": None
        }
    }

    # === Step 3: Call Quote API ===
    response = requests.post(quote_url, headers=headers, json=payload)
    response.raise_for_status()
    quote_data = response.json()

    df = pd.json_normalize(quote_data)
    return df

def weight_to_lbs(weight):
    return float(weight) * 2.205

def jbhunt_api(origin_zip, destination_zip, weight):

    weight_lbs = weight_to_lbs(weight)
    df = get_jbhunt_quote_df(origin_zip, destination_zip, weight_lbs)
    if df.empty or "rates" not in df.columns:
        return None

    # Extract the first row's rates list
    rates_list = df["rates"].iloc[0] if not df["rates"].isna().iloc[0] else []

    if not rates_list:
        return None

    # Find the quote with the lowest totalCharge value
    lowest_quote = min(rates_list, key=lambda x: x.get("totalCharge", {}).get("value", float("inf")))

    return {
        "Rate": lowest_quote["totalCharge"]["value"],
        "Carrier Name": lowest_quote.get("scacCode", "Unknown"),
        "Mode": lowest_quote.get("transportationMode", "Unknown"),
        "Service Provider": "J.B. Hunt"
    }
