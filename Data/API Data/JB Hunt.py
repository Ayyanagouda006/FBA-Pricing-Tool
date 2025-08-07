#!/usr/bin/env python
# coding: utf-8

# In[2]:


import requests
import pandas as pd
from datetime import datetime, timedelta
import os
from tqdm import tqdm

LOG_FILE = r"D:\Ayyanagouda\Last Mile Rates\Logs\jbhunt_api_tracking.xlsx"

def log_jbhunt_quote(origin_zip, destination_zip, weight_lbs, status, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "Timestamp": timestamp,
        "Origin ZIP": str(origin_zip),
        "Destination ZIP": str(destination_zip),
        "Weight (lbs)": weight_lbs,
        "Status": status,  # "Success" or "Failed"
        "Message": message
    }

    if os.path.exists(LOG_FILE):
        df = pd.read_excel(LOG_FILE)
    else:
        df = pd.DataFrame(columns=list(log_entry.keys()))

    df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
    df.to_excel(LOG_FILE, index=False)


def get_jbhunt_quote_df(origin_zip, destination_zip, weight_lbs):
    try:
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
            "billToCode": "AGCH0U",
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

    except Exception as e:
        log_jbhunt_quote(origin_zip, destination_zip, weight_lbs, "Failed", str(e))
        return None


def weight_to_lbs(weight):
    return float(weight) * 2.205


def jbhunt_api(origin_zip, destination_zip, weight):
    weight_lbs = weight_to_lbs(weight)
    df = get_jbhunt_quote_df(origin_zip, destination_zip, weight_lbs)

    if df is None or df.empty or "rates" not in df.columns:
        log_jbhunt_quote(origin_zip, destination_zip, weight_lbs, "Failed", "No valid rates returned")
        return {"error": "Exception occurred", "message": "No valid rates returned"}

    rates_list = df["rates"].iloc[0] if not df["rates"].isna().iloc[0] else []

    if not rates_list:
        log_jbhunt_quote(origin_zip, destination_zip, weight_lbs, "Failed", "Empty rates list")
        return {"error": "Exception occurred", "message": "Empty rates list"}

    lowest_quote = min(rates_list, key=lambda x: x.get("totalCharge", {}).get("value", float("inf")))
    rate = lowest_quote.get("totalCharge", {}).get("value")
    carrier = lowest_quote.get("scacCode", "Unknown")

    log_jbhunt_quote(origin_zip, destination_zip, weight_lbs, "Success", f"Rate: {rate}, Carrier: {carrier}")

    return {
        "Rate": rate,
        "Carrier Name": carrier,
        "Service Provider": "J.B. Hunt"
    }

# Read the template
template = pd.read_excel(r"D:\Ayyanagouda\Last Mile Rates\Data\API Data\Template for last mile rates.xlsx")

response_rows = []

for i, rows in tqdm(template.iterrows(), total=len(template), desc="Origin-Destination Pairs"):
    fpod_zip = str(rows['Origin ZIP']).zfill(5)
    fpod_city = rows['Origin City']
    fpod_state_code = rows['Origin State Code']
    fba_code = rows['FBA Code']
    fba_zip = str(rows['FBA or Destination ZIP']).zfill(5)
    fba_city = rows['Destn City']
    fba_state_code = rows['Destn State Code']
    pallets = rows['Num Of Pallet']
    weight = pallets * 1000

    result = jbhunt_api(fpod_zip, fba_zip, weight)

    # Handle response safely
    if "Lowest Rate" in result and "Carrier Name" in result:
        rate = result["Lowest Rate"]
        carrier = result["Carrier Name"]
    else:
        rate = None
        carrier = None

    response_rows.append({
        'FPOD ZIP': fpod_zip,
        'FPOD CITY': fpod_city,
        'FPOD STATE CODE': fpod_state_code,
        'FBA Code': fba_code,
        'FBA ZIP': fba_zip,
        'FBA CITY': fba_city,
        'FBA STATE CODE': fba_state_code,
        'Pallets': pallets,
        'Weight': weight,
        'Rate': rate,
        'Carrier Name': carrier
    })



# Convert to DataFrame
response = pd.DataFrame(response_rows)

response = pd.DataFrame(response_rows)
response.to_excel(r"D:\Ayyanagouda\Last Mile Rates\Data\API Data\jbhunt_output.xlsx")


# In[3]:





# In[4]:





# In[ ]:




