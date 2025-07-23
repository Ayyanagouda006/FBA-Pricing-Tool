import requests
import pandas as pd

def exfreight_api(origin, destination, weight, qty):
    url = "https://exfreight.flipstone.com/api/v2/rating"

    headers = {
        "Authorization": "token 84fab4ca8d33fc1b",
        "Exfresso-Partner-Id": "20b81740-778e-43fd-8dfe-722c35179aab",
        "Content-Type": "application/json"
    }

    payload = {
        "username": "anshul.marele@agraga.com",
        "pickup": {"country": "US", "postal": origin},
        "delivery": {"country": "US", "postal": destination},
        "ship_day": "2025-07-22",
        "ltl": {
            "accessorials": [
                {"category": "amazon_fba_delivery", "scope": "at_delivery"},
                {"category": "ocean_cfs_pickup", "scope": "at_pickup"}
            ],
            "freight_class": "85",
            "items": [
                {
                    "description": "GENERAL",
                    "dimensioned_pieces": {
                        "height": {"unit": "inch", "value": 72},
                        "length": {"unit": "inch", "value": 48},
                        "quantity": qty,
                        "width": {"unit": "inch", "value": 40}
                    },
                    "is_hazardous": False,
                    "total_weight": {"unit": "kilogram", "value": weight}
                }
            ]
        },
        "product": "all",
        "result_filtering": None
    }

    response = requests.post(url, headers=headers, json=payload)

    if not response.ok:
        return {"error": f"API error: {response.status_code}", "message": response.text}

    data = response.json()

    if "routes" not in data or not data["routes"]:
        return {"error": "No routes returned by API", "raw_response": data}

    rows = []
    for route in data['routes']:
        try:
            row = {
                'Carrier Name': route['legs'][0]['carrier']['name'],
                'SCAC': route['scac'],
                'Quote Reference ID': route['bill_of_lading_details'].get('carrier_quote_reference_id'),
                'Service Description': route['bill_of_lading_details'].get('carrier_service_description'),
                'Pickup Date': route['legs'][0].get('scheduled_pickup_date'),
                'Delivery Date': route['legs'][0].get('scheduled_delivery_date'),
                'Transit Days': route.get('transit_days'),
                'Total Charge (USD)': route['total_charge']['value'] / 100,
                'Reliability (%)': route.get('overall_on_time_reliability'),
                'Valid Until': route.get('valid_until'),
                'Freight Charge': next((item['charge']['value'] / 100 for item in route['line_item_charges'] if 'Freight' in item['description']), 0),
                'FBA Delivery Charge': next((item['charge']['value'] / 100 for item in route['line_item_charges'] if 'FBA Delivery' in item['description']), 0),
            }
            rows.append(row)
        except Exception as e:
            print(f"Error processing route: {e}")
            continue

    if not rows:
        return {"error": "No valid rate rows parsed", "raw_response": data}

    df = pd.DataFrame(rows)
    best_rate = df.nsmallest(1, 'Total Charge (USD)').iloc[0]

    return {
        "Lowest Rate": best_rate["Total Charge (USD)"],
        "Carrier Name": best_rate["Carrier Name"]
    }
