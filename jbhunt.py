import requests
import pandas as pd
from datetime import datetime, timedelta
import os

LOG_FILE = r"Logs/jbhunt_api_tracking.xlsx"

def log_jbhunt_quote(origin_zip, fba_code, destination_zip, weight_lbs, status, message, quote_id, source, date,unique_id,rate_type):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "Quotation Number": quote_id,
        'Unique ID':unique_id,
        "Timestamp": timestamp,
        "Origin ZIP": str(origin_zip),
        "FBA Code":fba_code,
        "Destination ZIP": str(destination_zip),
        "Weight (lbs)": weight_lbs,
        "Rate Type": rate_type,
        "Status": status,  # "Success" or "Failed"
        "Message": message,
        "Source": source,
        'Date':date
    }

    if os.path.exists(LOG_FILE):
        df = pd.read_excel(LOG_FILE)
    else:
        df = pd.DataFrame(columns=list(log_entry.keys()))

    df = pd.concat([df, pd.DataFrame([log_entry])], ignore_index=True)
    df.to_excel(LOG_FILE, index=False)


def get_jbhunt_quote_df(origin_zip, fba_code, destination_zip, weight_lbs,quote_id,today,unique_id,rate_type):
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
        log_jbhunt_quote(origin_zip, fba_code, destination_zip, weight_lbs, "Failed", str(e), quote_id, "",today,unique_id,rate_type)
        return None



def api(origin_zip, fba_code, destination_zip, weight_lbs, quote_id,unique_id,rate_type):
    today = datetime.today().date().strftime("%d-%m-%Y")
    df = get_jbhunt_quote_df(origin_zip, fba_code, destination_zip, weight_lbs, quote_id,today,unique_id,rate_type)

    if df is None or df.empty or "rates" not in df.columns:
        log_jbhunt_quote(origin_zip, fba_code, destination_zip, weight_lbs, "Failed", "No valid rates returned", quote_id, "",today,unique_id,rate_type)
        return {
            "Rate Type": rate_type,
            "Rate": 0,
            "Carrier Name": "Jb Hunt API Failed :No valid rates returned",
            "Service Provider": "J.B. Hunt",
            "Source":"API",
            "Date":today
        }

    rates_list = df["rates"].iloc[0] if not df["rates"].isna().iloc[0] else []

    if not rates_list:
        log_jbhunt_quote(origin_zip, fba_code, destination_zip, weight_lbs, "Failed", "Empty rates list", quote_id, "",today,unique_id,rate_type)
        return {
            "Rate Type": rate_type,
            "Rate": 0,
            "Carrier Name": "Jb Hunt API Failed :No valid rates returned",
            "Service Provider": "J.B. Hunt",
            "Source":"API",
            "Date":today
        }

    lowest_quote = min(rates_list, key=lambda x: x.get("totalCharge", {}).get("value", float("inf")))
    rate = lowest_quote.get("totalCharge", {}).get("value")
    carrier = lowest_quote.get("scacCode", "Unknown")

    log_jbhunt_quote(origin_zip, fba_code, destination_zip, weight_lbs, "Success", f"Rate: {float(rate) * 1.5}, Carrier: {carrier}", quote_id, "API",today,unique_id,rate_type)

    return {
        "Rate Type": rate_type,
        "Rate": float(rate) * 1.5,
        "Carrier Name": carrier,
        "Service Provider": "J.B. Hunt",
        "Source":"API",
        "Date":today
    }

def jbhunt_api(origin_zip, fba_code, destination_zip, weight, quote_id,unique_id,rate_type):
    df = pd.read_excel(r"Data/API Data/jbhunt_output.xlsx")

    origin_zip = str(origin_zip).zfill(5)
    destination_zip = str(destination_zip).zfill(5)
    df['FPOD ZIP'] = df['FPOD ZIP'].astype(str).str.zfill(5)
    df['FBA ZIP'] = df['FBA ZIP'].astype(str).str.zfill(5)
    # Filter matching rows
    match = df[
        (df['FPOD ZIP'] == origin_zip) &
        (df['FBA ZIP'] == destination_zip) &
        (df['Weight'] == weight)
    ]
    match["Valid From"] = pd.to_datetime(match["Valid From"], format="%d-%m-%Y", errors="coerce")
    match["Valid To"] = pd.to_datetime(match["Valid To"], format="%d-%m-%Y", errors="coerce")

    if not match.empty:
        today = pd.to_datetime(datetime.today().strftime("%d-%m-%Y"), format="%d-%m-%Y")
        valid_rows = match[
            match['Rate'].notna() & (match['Rate'] != '') & (match['Rate'].astype(float) != 0.0) &
            (match['Valid From'] <= today) & (match['Valid To'] >= today)
        ]

        if not valid_rows.empty:
            # Convert Rate to float before sorting to avoid string-based sorting
            valid_rows['Rate'] = valid_rows['Rate'].astype(float)
            # Sort in ascending order of Rate
            valid_rows = valid_rows.sort_values(by='Rate', ascending=True).reset_index(drop=True)

            row = valid_rows.iloc[0]
            log_jbhunt_quote(origin_zip, fba_code, destination_zip, weight, 
                             "Success", f'Rate: {float(row["Rate"]) * 1.5}, Carrier: {row["Carrier Name"]}',
                               quote_id, "API STATIC DATA", row['Date Modified'],unique_id,rate_type)
            return {
                "Rate Type": rate_type,
                "Rate": float(row["Rate"]) * 1.5,
                "Carrier Name": row["Carrier Name"],
                "Service Provider": "J.B. Hunt",
                "Source":"API STATIC DATA",
                "Date":row['Date Modified']
            }

    # Fallback to API
    return api(origin_zip, fba_code, destination_zip, weight, quote_id,unique_id,rate_type)
