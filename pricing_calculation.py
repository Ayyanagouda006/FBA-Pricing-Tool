import re
import pandas as pd
from heyprimo import heyprimo_api
from exfreight import exfreight_api
from jbhunt import jbhunt_api
from math import ceil
import os
from datetime import datetime

exchange_rate=88


def log_booking(booking_id, quotation_no, unique_id, output1, output2, log_file):

    # --- Add metadata ---
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary_df = output1.copy()
    breakdown_df = output2.copy()

    for df in [summary_df, breakdown_df]:
        df["Booking ID"] = booking_id
        df["Quotation Number"] = quotation_no
        df['Unique ID'] = unique_id
        df["Log Timestamp"] = timestamp

    # --- Load existing log ---
    if os.path.exists(log_file):
        try:
            existing_summary = pd.read_excel(log_file, sheet_name="Summary")
        except Exception:
            existing_summary = pd.DataFrame()

        try:
            existing_breakdown = pd.read_excel(log_file, sheet_name="Breakdown")
        except Exception:
            existing_breakdown = pd.DataFrame()

        # Append fresh data
        updated_summary = pd.concat([existing_summary, summary_df], ignore_index=True)
        updated_breakdown = pd.concat([existing_breakdown, breakdown_df], ignore_index=True)

    else:
        # Start fresh log
        updated_summary = summary_df
        updated_breakdown = breakdown_df

    # --- Save both sheets ---
    with pd.ExcelWriter(log_file, engine="openpyxl") as writer:
        updated_summary.to_excel(writer, sheet_name="Summary", index=False)
        updated_breakdown.to_excel(writer, sheet_name="Breakdown", index=False)

    print(f"✅ Booking {booking_id} for quotation {quotation_no} logged successfully.")



def summarization(data, quote_id, booking_counter):
    # Step 1: Flatten nested dict into rows
    rows = []
    for dest, modes in data.items():
        for mode, details in modes.items():
            rows.append({
                'Unique ID':details.get("Unique ID", ""),
                "Origin Address": details.get("Origin", ""),
                "POL": details.get("POL", ""),
                "P2P Type": mode,
                "Consolidator": details.get("Consolidator", ""),
                "FBA / Destn Coast": details.get("coast",""),
                "FPOD": details.get("POD", ""),
                "FBA / Destn": details.get("FBA Code", ""),
                "FBA / Destn Address": details.get("FBA Address", ""),
                "Category": details.get("category", ""),
                "CBM": details.get("Total CBM", 0.0),
                "#Pallets": details.get("Total Pallets", 0.0),
                "Service Modes":details.get("Service Modes", 0.0),
                "LM Delivery Type": details.get("Selected lm", {}).get("Rate Type", ""),
                "LM Loadability":details.get("LM Loadability", 0.0),
                "LM Rate": details.get("Selected lm", {}).get("Rate", 0.0),
                "LM Broker": details.get("Selected lm", {}).get("Service Provider", ""),
                "LM Carrier": details.get("Selected lm", {}).get("Carrier Name", ""),
                "1st Mile": details.get("Pick-Up Charges", 0.0),
                "OCC": details.get("OCC", 0.0),
                "DCC": details.get("DCC", 0.0),
                "P2P": details.get("PER CBM P2P", 0.0),
                "Documentation": details.get("Documentation", 0.0),
                "Palletization Cost": details.get("Palletization Cost", 0.0),
                "Quotation Total CBM" : details.get("Quotation Total CBM",0.0)
            })

    df_all = pd.DataFrame(rows)

    results = {}
    # Create logs folder if it doesn't exist
    os.makedirs("Logs", exist_ok=True)
    log_file = "Logs/bookings_log.xlsx"

    # Step 2: Group by FPOD and Category
    for (fpod, category), df_group in df_all.groupby(["FPOD", "Category"]):
        orows = []

        unique_id = list(df_group['Unique ID'].unique())[0]
        first_mile = df_group["1st Mile"].astype(float).max()
        quote_tot_cbm = df_group["Quotation Total CBM"].astype(float).max()
        first_mile_pcbm = float(first_mile) / float(quote_tot_cbm)
        occ = df_group["OCC"].astype(float).max()
        dcc = df_group["DCC"].astype(float).max()
        tot_cbm = df_group["CBM"].sum()
        tot_first_mile = float(first_mile_pcbm) * float(tot_cbm)
        pallets = df_group["#Pallets"].sum()
        pal_pp = df_group["Palletization Cost"].astype(float).max()
        lm_delivery_type = list(df_group["LM Delivery Type"].unique())

        # Step 3: P2P per FPOD (inside group)
        P2P_dict = {}
        for fpod_inner, group_inner in df_group.groupby("FPOD"):
            total_cbm = group_inner["CBM"].sum()
            total_doc = group_inner["Documentation"].max()
            avg_p2p = group_inner["P2P"].max()
            doc_per_cbm = total_doc / total_cbm if total_cbm else 0.0
            total_p2p = avg_p2p + doc_per_cbm
            P2P_dict[fpod_inner] = {"CBM": total_cbm, "Total P2P": total_p2p}

        # Step 4: LM per FBA code
        lm = {}
        for _, row in df_group.iterrows():
            fba_code = row["FBA / Destn"]
            if fba_code not in lm:
                lm[fba_code] = {"Rate": 0.0, "CBM": 0.0}
            lm[fba_code]["Rate"] += float(row["LM Rate"])
            lm[fba_code]["CBM"] += float(row["CBM"])
            lm[fba_code]["LM Delivery Type"] = row["LM Delivery Type"]
            lm[fba_code]['LM Loadability'] = row['LM Loadability']
            lm[fba_code]["Service Modes"] = row["Service Modes"]

        # Step 5: Charge Heads
        orows.append({
            "Charge Heads": "1St Mile",
            "Basis": "As per Vendor",
            "Basis QTY": "",
            "Charge In $": tot_first_mile,
            "Exchange Rate (USD to INR)": exchange_rate,
            "Per CBM In $": first_mile_pcbm,
            "Charge in INR": tot_first_mile * exchange_rate,
            "Per CBM in INR": first_mile_pcbm * exchange_rate
        })

        occ_pcbm = float(occ) / float(tot_cbm)
        orows.append({
            "Charge Heads": "OCC",
            "Basis": "Flat (Per Quote)",
            "Basis QTY": "",
            "Charge In $": occ,
            "Exchange Rate (USD to INR)": exchange_rate,
            "Per CBM In $": occ_pcbm,
            "Charge in INR": occ * exchange_rate,
            "Per CBM in INR": occ_pcbm * exchange_rate
        })

        dcc_pcbm = float(dcc) / float(tot_cbm)
        orows.append({
            "Charge Heads": "DCC",
            "Basis": "Flat (Per Quote)",
            "Basis QTY": "",
            "Charge In $": dcc,
            "Exchange Rate (USD to INR)": exchange_rate,
            "Per CBM In $": dcc_pcbm,
            "Charge in INR": dcc * exchange_rate,
            "Per CBM in INR": dcc_pcbm * exchange_rate
        })

        for fpod_inner, value in P2P_dict.items():
            cal_p2p = float(value['Total P2P']) * float(value['CBM'])
            orows.append({
                "Charge Heads": f"P2P({fpod_inner})",
                "Basis": "Per CBM",
                "Basis QTY": value['CBM'],
                "Charge In $": cal_p2p,
                "Exchange Rate (USD to INR)": exchange_rate,
                "Per CBM In $": value['Total P2P'],
                "Charge in INR": cal_p2p * exchange_rate,
                "Per CBM in INR": float(value['Total P2P']) * exchange_rate
            })

        if "Drayage" not in lm_delivery_type:
            pal_pcbm = float(pal_pp)/ float(tot_cbm)
            orows.append({
                "Charge Heads": "Palletization",
                "Basis": "Per Pallet",
                "Basis QTY": pallets,
                "Charge In $": pal_pp,
                "Exchange Rate (USD to INR)": exchange_rate,
                "Per CBM In $": pal_pcbm,
                "Charge in INR": pal_pp * exchange_rate,
                "Per CBM in INR": float(pal_pcbm) * exchange_rate
            })

        for fba_code, value in lm.items():
            lm_rate = value["Rate"]
            lm_cbm = value["CBM"]
            service_modes = value["Service Modes"]
            if value["LM Delivery Type"] == "Drayage":
                loadability = value['LM Loadability']
                lm_pcbm = float(lm_rate) / float(loadability)
                charge_lm = float(lm_pcbm) * float(lm_cbm)
                if charge_lm >= 120.0:
                    charge_lm = charge_lm
                    lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                else:
                    if charge_lm != 0:
                        charge_lm = 120.0
                        lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                    else:
                        charge_lm = 0.0
                        lm_rate_pcbm = 0.0
            else:
                if set(service_modes) == {"FTL", "FTL53"}:
                    charge_lm = float(lm_rate) * float(lm_cbm)
                    if charge_lm >= 120.0:
                        charge_lm = charge_lm
                        lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                    else:
                        if charge_lm != 0:
                            charge_lm = 120.0
                            lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                        else:
                            charge_lm = 0.0
                            lm_rate_pcbm = 0.0
                elif set(service_modes) == {"FTL53"}:
                    
                    charge_lm = float(lm_rate) * float(lm_cbm)
                    if charge_lm >= 120.0:
                        charge_lm = charge_lm
                        lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                    else:
                        if charge_lm != 0:
                            charge_lm = 120.0
                            lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                        else:
                            charge_lm = 0.0
                            lm_rate_pcbm = 0.0
                else:
                    
                    charge_lm = lm_rate
                    if charge_lm >= 120.0:
                        charge_lm = charge_lm
                        lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                    else:
                        if charge_lm != 0:
                            charge_lm = 120.0
                            lm_rate_pcbm = float(charge_lm) / float(lm_cbm)
                        else:
                            charge_lm = 0.0
                            lm_rate_pcbm = 0.0

            orows.append({
                "Charge Heads": f"Last Mile({fba_code})",
                "Basis": "Per CBM",
                "Basis QTY": lm_cbm,
                "Charge In $": charge_lm,
                "Exchange Rate (USD to INR)": exchange_rate,
                "Per CBM In $": lm_rate_pcbm,
                "Charge in INR": charge_lm * exchange_rate,
                "Per CBM in INR": float(lm_rate_pcbm) * exchange_rate
            })

        # Final total
        output2 = pd.DataFrame(orows)
        total_percbm = output2["Charge In $"].sum() / tot_cbm if tot_cbm else 0.0
        total_charge = output2["Charge In $"].sum()
        total_row = {
            "Charge Heads": "Total",
            "Basis": "Per CBM",
            "Basis QTY": tot_cbm,
            "Charge In $": total_charge ,
            "Exchange Rate (USD to INR)": "",
            "Per CBM In $": total_percbm,
            "Charge in INR": total_charge * exchange_rate,
            "Per CBM in INR": total_percbm * exchange_rate
        }
        output2 = pd.concat([output2, pd.DataFrame([total_row])], ignore_index=True)
        output2 = output2.round(2)

        # Clean output1
        output1 = df_group[[
            "Origin Address", "POL", "P2P Type", "Consolidator", "FBA / Destn Coast", "FPOD",
            "FBA / Destn", "FBA / Destn Address", "Category", "CBM", "#Pallets", "LM Delivery Type",
            "LM Broker", "LM Carrier", "LM Rate"
        ]]

        # --- Booking Logging ---
        log_booking(f"Booking {booking_counter}", quote_id, unique_id, output1, output2, log_file)

        # -----------------------

        results[f"Booking {booking_counter}"] = [output1, output2]
        booking_counter += 1

    return results, booking_counter



def ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_code, fba_city, fba_st_code, fba_zip, qty, weight,quote_id,unique_id):
    # Read offline last mile rates
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    lm = lm[lm['Delivery Type'] == "LTL"]

    # Step 1: Get API results
    hp_result = heyprimo_api({
        "Origin City": fpod_city,
        "Origin State Code": fpod_st_code,
        "Origin ZIP": fpod_zip,
        "Destn City": fba_city,
        "Destn State Code": fba_st_code,
        "FBA Code": fba_code,
        "FBA or Destination ZIP": fba_zip,
        "Num Of Pallet": qty,
        "quote_id":quote_id,
        'unique id':unique_id
    })

    ef_result = exfreight_api(fpod_zip, fba_code, fba_zip, weight, qty, quote_id, unique_id)

    # Step 2: Parse rates from API safely
    candidates = []

    if isinstance(hp_result, dict) and "Lowest Rate" in hp_result:
        candidates.append({
            "Rate Type": "LTL",
            "Rate": round(float(hp_result["Lowest Rate"]), 2),
            "Carrier Name": hp_result.get("Carrier Name", ""),
            "Service Provider": "HeyPrimo",
            "Source": hp_result.get("Source", ""),   # safe default
            "Date": hp_result.get("Date", "")
        })


    if isinstance(ef_result, dict) and "Lowest Rate" in ef_result:
        candidates.append({
            "Rate Type": "LTL",
            "Rate": round(float(ef_result["Lowest Rate"]), 2),
            "Carrier Name": ef_result.get("Carrier Name", ""),
            "Service Provider": "Ex-Freight",
            "Source": ef_result.get("Source", ""),   # ✅ use ef_result not hp_result
            "Date": ef_result.get("Date", "")
        })


    # Step 3: Find offline Excel rates (exact match by zip + pallet count)
    try:
        today = pd.to_datetime(datetime.today().strftime("%d-%m-%Y"), format="%d-%m-%Y")
        lm["Valid From"] = pd.to_datetime(lm["Valid From"], format="%d-%m-%Y", errors="coerce")
        lm["Valid To"] = pd.to_datetime(lm["Valid To"], format="%d-%m-%Y", errors="coerce")
        offline_match = lm[
            (lm['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
            (lm['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
            (lm['No. of pallets'] == qty) &
            (lm['Valid From'] <= today) & (lm['Valid To'] >= today)
        ]

        for _, row in offline_match.iterrows():
            candidates.append({
                "Rate Type": "LTL",
                "Rate": round(float(row['Rate']), 2),
                "Carrier Name": row['Carrier Name'] if not pd.isna(row['Carrier Name']) else "",
                "Service Provider": row["Broker"] if not pd.isna(row['Broker']) else "",
                "Source":"No API STATIC DATA",
                "Date":row['Date Modified'] if not pd.isna(row['Date Modified']) else ""
            })
    except Exception as e:
        print("Error matching offline Excel rate:", e)

    # Step 4: Pick the lowest rate
    if candidates:
        return min(candidates, key=lambda x: x["Rate"])
    else:
        return None
    
def ftl_rate(fpod_zip, fba_code, fba_zip, qty, quote_id,unique_id):
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    today = pd.to_datetime(datetime.today().strftime("%d-%m-%Y"), format="%d-%m-%Y")
    lm["Valid From"] = pd.to_datetime(lm["Valid From"], format="%d-%m-%Y", errors="coerce")
    lm["Valid To"] = pd.to_datetime(lm["Valid To"], format="%d-%m-%Y", errors="coerce")

    # Separate FTL and FTL53 sheets
    lm_ftl = lm[lm['Delivery Type'] == "FTL"]
    lm_ftl53 = lm[lm['Delivery Type'] == "FTL53"]

    ftl_cand = []
    ftl_match = lm_ftl[
        (lm_ftl['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
        (lm_ftl['Valid From'] <= today) & (lm_ftl['Valid To'] >= today)
    ]

    for _, row in ftl_match.iterrows():
        ftl_cand.append({
            "Rate Type": "FTL",
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'] if not pd.isna(row['Carrier Name']) else "",
            "Service Provider": row["Broker"] if not pd.isna(row['Broker']) else "",
            "Source":"No API STATIC DATA",
            "Date":row['Date Modified'] if not pd.isna(row['Date Modified']) else ""
        })

    ftl_jb = jbhunt_api(fpod_zip, fba_code, fba_zip, "11024", quote_id,unique_id,"FTL")
    ftl_cand.append(ftl_jb)

    ftl53_cand = []
    ftl53_match = lm_ftl53[
        (lm_ftl53['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl53['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
        (lm_ftl53['Valid From'] <= today) & (lm_ftl53['Valid To'] >= today)
    ]

    for _, row in ftl53_match.iterrows():
        ftl53_cand.append({
            "Rate Type": "FTL53",
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'] if not pd.isna(row['Carrier Name']) else "",
            "Service Provider": row["Broker"] if not pd.isna(row['Broker']) else "",
            "Source":"No API STATIC DATA",
            "Date":row['Date Modified'] if not pd.isna(row['Date Modified']) else ""
        })

    ftl53_jb = jbhunt_api(fpod_zip, fba_code, fba_zip, "45000", quote_id,unique_id,"FTL53")
    ftl53_cand.append(ftl53_jb)
    # Safely return min if any rates were found, else None
    best_ftl = min(ftl_cand, key=lambda x: x["Rate"]) if ftl_cand else None
    best_ftl53 = min(ftl53_cand, key=lambda x: x["Rate"]) if ftl53_cand else None

    return best_ftl, best_ftl53

def rates_comparison(fpod_city, fpod_st_code, fpod_zip, fba_code, fba_city, fba_st_code, fba_zip,
                     total_pallet_count, weight, category, service_modes, quote_id, unique_id):
    drayage = None
    ltl = None
    ftl = None
    ftl53 = None

    # Special case for HOT category
    if set(service_modes) == {"Drayage"}:
        drayage = jbhunt_api(fpod_zip, fba_code, fba_zip, "45000", quote_id, unique_id,"Drayage")
        drayage_lowest = {
            "Rate Type": drayage.get("Rate Type"),
            "Rate": drayage.get("Rate"),
            "Carrier Name": drayage.get("Carrier Name"),
            "Service Provider": drayage.get("Service Provider"),
            "Source":drayage.get("Source"),
            "Date":drayage.get("Date")
        }
        return None, None, None, drayage_lowest, drayage_lowest, drayage_lowest

    # --- CASE 1: ["FTL", "FTL53"] ---
    if set(service_modes) == {"FTL", "FTL53"}:
        ftl_result, ftl53_result = ftl_rate(fpod_zip, fba_code, fba_zip, total_pallet_count, quote_id,unique_id)

        # Safe rate division if dict and valid
        if isinstance(ftl_result, dict) and isinstance(ftl_result.get("Rate"), (int, float)) and ftl_result["Rate"] > 0:
            ftl_result["Rate"] /= 21
        if isinstance(ftl53_result, dict) and isinstance(ftl53_result.get("Rate"), (int, float)) and ftl53_result["Rate"] > 0:
            ftl53_result["Rate"] /= 21

        rates = {
            "FTL": ftl_result if isinstance(ftl_result, dict) else None,
            "FTL53": ftl53_result if isinstance(ftl53_result, dict) else None
        }

        lowest_mode = min(rates, key=lambda m: rates[m]["Rate"] if rates[m] and isinstance(rates[m].get("Rate"), (int, float)) else float("inf"))
        lowest_rate_data = rates.get(lowest_mode) or {}

        lowest = selected_lowest = {
            "Rate Type": lowest_mode,
            "Rate": lowest_rate_data.get("Rate", 0.0),
            "Carrier Name": lowest_rate_data.get("Carrier Name", ""),
            "Service Provider": lowest_rate_data.get("Service Provider", ""),
            "Source":lowest_rate_data.get("Source"),
            "Date":lowest_rate_data.get("Date")
        }
        return None, ftl_result, ftl53_result, None, lowest, selected_lowest

    # --- CASE 2: ["FTL53"] ---
    if set(service_modes) == {"FTL53"}:
        _, ftl53_result = ftl_rate(fpod_zip,fba_code, fba_zip, total_pallet_count,quote_id,unique_id)
        if isinstance(ftl53_result, dict) and isinstance(ftl53_result.get("Rate"), (int, float)) and ftl53_result["Rate"] > 0:
            ftl53_result["Rate"] /= 48

        lowest = selected_lowest = {
            "Rate Type": "FTL53",
            "Rate": ftl53_result.get("Rate", 0.0) if isinstance(ftl53_result, dict) else 0.0,
            "Carrier Name": ftl53_result.get("Carrier Name", "") if isinstance(ftl53_result, dict) else "",
            "Service Provider": ftl53_result.get("Service Provider", "") if isinstance(ftl53_result, dict) else "",
            "Source":ftl53_result.get("Source","") if isinstance(ftl53_result, dict) else "",
            "Date":ftl53_result.get("Date") if isinstance(ftl53_result, dict) else ""
        }
        return None, None, ftl53_result, None, lowest, selected_lowest


    # --- CASE 3: Other combinations (with LTL or more) ---
    if "LTL" in service_modes:
        ltl = ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_code, fba_city, fba_st_code, fba_zip,
                       total_pallet_count, weight, quote_id,unique_id)

    if "FTL" in service_modes or "FTL53" in service_modes:
        ftl_result, ftl53_result = ftl_rate(fpod_zip, fba_code,fba_zip, total_pallet_count, quote_id,unique_id)
        if "FTL" in service_modes:
            ftl = ftl_result
        if "FTL53" in service_modes:
            ftl53 = ftl53_result

    # Compare only modes present in service_modes
    service_rates = {
        "LTL": ltl,
        "FTL": ftl,
        "FTL53": ftl53,
        "Drayage": drayage
    }
    valid_rates = {
        mode: data
        for mode, data in service_rates.items()
        if mode in service_modes and isinstance(data, dict)
        and isinstance(data.get("Rate"), (int, float)) and data["Rate"] > 0
    }

    if valid_rates:
        min_mode = min(valid_rates, key=lambda m: valid_rates[m]["Rate"])
        lowest = selected_lowest = {
            "Rate Type": min_mode,
            "Rate": valid_rates[min_mode]["Rate"],
            "Carrier Name": valid_rates[min_mode].get("Carrier Name", ""),
            "Service Provider": valid_rates[min_mode].get("Service Provider", ""),
            "Source":valid_rates[min_mode].get("Source", ""),
            "Date":valid_rates[min_mode].get("Date", "")
        }
    else:
        lowest = selected_lowest = {
            "Rate Type": "N/A",
            "Rate": 0.0,
            "Carrier Name": "",
            "Service Provider": "",
            "Source":"",
            "Date":""
        }

    return ltl, ftl, ftl53, drayage, lowest, selected_lowest


def classify_fba_code(fba_locations: pd.DataFrame, fba_code: str, quote_cbm: float, services) -> str:

    # Filter the DataFrame to the relevant FBA code
    sub_df = fba_locations[fba_locations["FBA Code"] == fba_code]
    sub_df["Pre-Determined Bucket"] = sub_df["Pre-Determined Bucket"].fillna("").astype(str).str.upper()
    Consolidator = sub_df["Consolidator"].values[0]
    coast = sub_df["FBA / Destn Coast"].values[0]
    Loadability = sub_df["Loadability"].values[0]
    last_3_weeks_avg = sub_df['Last 3 Week'].values[0]

    if sub_df.empty:
        if services is None:
            return "NON HOT", ["FTL", "FTL53", "LTL"], Consolidator, coast, 0.0
        else:
            return "NON HOT", services, Consolidator, coast, 0.0

    # Check for Pre-Determined Bucket
    pre_determined = sub_df["Pre-Determined Bucket"].values[0]
    
    if pd.notna(pre_determined) and str(pre_determined).strip() != "" and str(pre_determined) == "HOT":
        if services == []:
            return str(pre_determined).strip().upper(), ["Drayage"], Consolidator, coast, float(Loadability)
        else:
            return str(pre_determined).strip().upper(), services, Consolidator, coast, float(Loadability)


    if quote_cbm >= 50 :
        return "HOT", ["Drayage"], Consolidator, coast, quote_cbm
    else:
        if 15.0 < float(last_3_weeks_avg) <= 35.0:
            if services == []:
                return "NON HOT", ["FTL", "FTL53"], Consolidator, coast, 0.0
            else:
                return "NON HOT", services, Consolidator, coast, 0.0
        elif float(last_3_weeks_avg) > 35.0:
            if services == []:
                return "NON HOT", ["FTL53"], Consolidator, coast, 0.0
            else:
                return "NON HOT", services, Consolidator, coast, 0.0
        else:
            if services == []:
                return "NON HOT", ["FTL", "FTL53", "LTL"], Consolidator, coast, 0.0
            else:
                return "NON HOT", services, Consolidator, coast, 0.0


def rates(origin, cleaned_data, console_selected, is_occ, is_dcc, des_val, shipment_scope, pickup_charges_inr, 
          selected_service, grand_total_weight, grand_total_cbm, quote_id,unique_id):
    
    pickup_charges = 0.0
    if shipment_scope == "Door-to-Door":
        if pickup_charges_inr in [0.0, "0.0", "", None]:
            return {}, ["Pickup charges are required for Door-to-Door shipment scope."], []
        else:
            pickup_charges = float(pickup_charges_inr) / float(exchange_rate)

    # Load Excel sheets
    try:
        fba_locations = pd.read_excel(r"Data/FBA Rates.xlsx", 'FBA Locations')
        p2p = pd.read_excel(r"Data/FBA Rates.xlsx", 'P2P')
        accessorials = pd.read_excel(r"Data/FBA Rates.xlsx", 'Accessorials')
        palletization = pd.read_excel(r"Data/FBA Rates.xlsx", 'Palletization')
    except Exception as e:
        return {}, [f"❌ Failed to load one or more Excel sheets: {e}"], []

    results = {}
    skipped_fba = []
    errors = []

    for dest in cleaned_data:
        destination_name = dest.get("destination", "")
        cargo_details = dest.get("cargoDetails", [])

        qty = 0
        weight = 0.0
        pallets = 0
        loose_cbm = 0.0
        total_cbm = 0.0

        for item in cargo_details:
            try:
                package = item.get("packageType", "")
                item_qty = int(item.get("numPackages", 0))
                item_wtppack = float(item.get("wtPerPackage", 0.0))
                item_volppack = float(item.get("volPerPackage", 0.0))
                length = float(item.get("length", 0.0))
                width = float(item.get("width", 0.0))
                height = float(item.get("height", 0.0))
                try:

                    item_totweight = float(item.get("totalWeight", 0.0))
                    if item_totweight == 0.0:
                        item_weight = item_qty * item_wtppack
                    else:
                        item_weight = item_totweight
                except (TypeError, ValueError):
                    if item_wtppack == 0.0:
                        item_weight = 0.0
                    else:
                        item_weight = item_qty * item_wtppack

                try:
                    item_tot = float(item.get("totalVolume", 0.0))
                    if item_tot == 0.0:
                        vol = (length*width*height)/1000000
                        item_cbm = item_qty * vol
                    else:
                        item_cbm = item_tot
                except (TypeError, ValueError):
                    if item_volppack == 0.0:
                        vol = (length*width*height)/1000000
                        item_cbm = item_qty * vol
                    else:
                        item_cbm = item_qty * item_volppack
                    
                # print(package,item_cbm)
                qty += item_qty
                weight += item_weight
                total_cbm += item_cbm

                if package.lower() == "pallet":
                    pallets += item_qty
                else:
                    loose_cbm += item_cbm
            except Exception as e:
                errors.append(f"❌ Error parsing cargo for {destination_name}: {e}")
                continue

        loose_as_pallets = ceil(loose_cbm / 1.8)
        total_pallet_count = pallets + loose_as_pallets

        fba_code = destination_name.split(" ")[0]
        if fba_code in ['IUST', 'IUSL', 'PBI3', 'TMB8', 'SCK8' ]:
            skipped_fba.append(fba_code)
            continue

        sub_fba_locations = fba_locations[fba_locations['FBA Code'] == fba_code]

        if sub_fba_locations.empty:
            errors.append(f"⚠️ FBA Code {fba_code} not found in FBA Locations sheet.")
            continue


        for i, row in sub_fba_locations.iterrows():
            fpod_zip = str(row['FPOD ZIP']).zfill(5)
            fpod_city = row['FPOD CITY']
            fpod_unloc = row['FPOD UNLOC']
            fpod_st_code = row['FPOD STATE CODE']
            fba_zip = str(row['FBA ZIP']).zfill(5)
            fba_city = row['FBA CITY']
            fba_st_code = row['FBA STATE CODE']

            try:
                category, services, Consolidator, coast, lmloadability = classify_fba_code(fba_locations, fba_code, total_cbm, selected_service)
            except Exception as e:
                category = "Unknown"
                Consolidator = ""
                coast = ""
                lmloadability = 0.0
                errors.append(f"⚠️ Error classifying FBA code {fba_code}: {e}")

            if console_selected == "not selected" and console_selected != "both selected":
                
                if fpod_unloc in ['USNYC', 'USCHS', 'USLAX', 'USJAX']:
                    console_type = 'Own Console'
                else:
                    if 'Drayage' in services:
                        console_type = 'Own Console'
                    else:
                        console_type = 'Coload'
            else:   
                console_type = console_selected

            try:
                ltl, ftl, ftl53, drayage, lowest, selected_lowest = rates_comparison(
                    fpod_city, fpod_st_code, fpod_zip, fba_code, 
                    fba_city, fba_st_code, fba_zip,
                    total_pallet_count, weight, category, services, quote_id, unique_id
                )
            except Exception as e:
                errors.append(f"❌ Rate comparison failed for {destination_name} (FBA {fba_code}): {e}")
                continue
            
            if console_type.lower() == "both selected":
                sub_p2p = p2p[p2p['FPOD UNLOC'] == fpod_unloc]
            else:
                sub_p2p = p2p[
                    (p2p['FPOD UNLOC'] == fpod_unloc) &
                    (p2p['P2P Type'].str.lower() == console_type.lower())
                ]

            if sub_p2p.empty:
                errors.append(f"⚠️ No P2P match found for FPOD {fpod_unloc}, console type: {console_type}")
                continue


            for j, prow in sub_p2p.iterrows():
                try:
                    pol = prow['POL Name']
                    pol_unloc = prow['POR/POL']
                    oc_p2p_inr = prow['Origin charges per Container(INR)']
                    of_p2p = prow['Ocean Freight (USD)']
                    dd_p2p = prow['Drayage & Devanning(USD)']
                    tcost_p2p = prow['Total cost (USD)']
                    p2ploadability = prow['Loadability']
                    


                    if "Drayage" in services and console_type == 'Own Console':
                        oc_p2p_usd = float(oc_p2p_inr)/float(exchange_rate)
                        t_p2p = float(oc_p2p_usd)+float(of_p2p)
                        percbm_p2p = t_p2p/p2ploadability
                    else:
                        percbm_p2p = prow['Per CBM(USD)']

                    # print(total_cbm)
                    if total_cbm >= 1:
                        total_cbm = total_cbm
                    else:
                        total_cbm = 1
                    
                    total_p2p = percbm_p2p * total_cbm
                    console = prow['P2P Type']

                    if shipment_scope == "Port-to-Door":
                        try:
                            origin_unloc = re.search(r'\((.*?)\)', origin).group(1)
                        except Exception as e:
                            errors.append(f"⚠️ Failed to parse POL from origin string '{origin}': {e}")
                            continue

                        if pol_unloc != origin_unloc:
                            continue

                    try:
                        pod_doc = accessorials[(accessorials["Location Unloc"] == fpod_unloc) &
                                                (accessorials["Charge Head"] == "Documentation")]["Amount"].values[0]
                        doc_pcbm = float(pod_doc)/float(total_cbm)
                    except IndexError:
                        errors.append(f"⚠️ Documentation charge missing for {fpod_unloc}")
                        pod_doc = 0
                        doc_pcbm = 0

                    try:
                        occ = accessorials[(accessorials["Location Unloc"] == pol_unloc) &
                                                (accessorials["Charge Head"] == "OCC")]["Amount"].values[0] if is_occ else 0
                    except IndexError:
                        if is_occ:
                            errors.append(f"⚠️ OCC charge missing for {pol_unloc}")
                        occ = 0

                    try:
                        dcc = accessorials[(accessorials["Location Unloc"] == fpod_unloc) &
                                                (accessorials["Charge Head"] == "DCC")]["Amount"].values[0] if is_dcc else 0
                    except IndexError:
                        if is_dcc:
                            errors.append(f"⚠️ DCC charge missing for {fpod_unloc}")
                        dcc = 0

                    try:
                        pal_cost = palletization[(palletization["FPOD UNLOC"] == fpod_unloc) &
                                                (palletization["Service Type"] == "Palletization cost Per Pallet")]["Amount"].values[0]
                        palletization_cost = float(pal_cost) * loose_as_pallets
                    except IndexError:
                        errors.append(f"⚠️ Palletization Cost missing for {fpod_unloc}")
                        pal_cost = 0.0
                        palletization_cost = 0.0

                    if destination_name not in results:
                        results[destination_name] = {}

                    if shipment_scope == "Door-to-Door":
                        gtotal = float(selected_lowest["Rate"]) + float(total_p2p) + float(pod_doc) + float(occ) + float(dcc) + float(pickup_charges) + float(palletization_cost)
                    else:
                        gtotal = float(selected_lowest["Rate"]) + float(total_p2p) + float(pod_doc) + float(occ) + float(dcc) + float(palletization_cost)

                    tot_pcbm = gtotal / total_cbm if total_cbm else 0

                    results[destination_name][console] = {
                        'Unique ID':unique_id,
                        "Shipment Scope":shipment_scope,
                        "Origin": origin,
                        "POL": pol,
                        "POD": fpod_city,
                        "POD Zip": fpod_zip,
                        "FBA Code": fba_code,
                        "FBA Address": destination_name,
                        "FBA Zip Code": fba_zip,
                        "Consolidator": Consolidator,
                        "coast": coast,
                        "Qty": qty,
                        "Total Weight": weight,
                        "Quotation Total Weight": grand_total_weight,
                        "Total CBM": total_cbm,
                        "Quotation Total CBM":grand_total_cbm, 
                        "Total Pallets": total_pallet_count,
                        "category": category,
                        "Service Modes": services,
                        "LM Loadability": lmloadability,
                        "LTL": ltl,
                        "FTL": ftl,
                        "FTL53": ftl53,
                        "Drayage": drayage,
                        'lowest lm': lowest,
                        'Selected lm': selected_lowest,
                        'Pick-Up Charges(INR)':pickup_charges_inr,
                        "Pick-Up Charges": pickup_charges,
                        "PER CBM P2P": percbm_p2p,
                        "PER CBM P2P & Doc": percbm_p2p + doc_pcbm,
                        "P2P Origin charges per Container(INR)":oc_p2p_inr,
                        "P2P Ocean Freight (USD)":of_p2p,
                        "P2P Drayage & Devanning(USD)":dd_p2p,
                        "P2P Total cost (USD)":tcost_p2p,
                        "P2P Loadability": p2ploadability,
                        "P2P Charge": total_p2p,
                        "Destination Doc": float(pod_doc),
                        "OCC": float(occ),
                        "DCC": float(dcc),
                        "Documentation": float(pod_doc),
                        "Palletization (Per Pallet)": float(pal_cost),
                        "Palletization Cost": + float(palletization_cost),
                        "Last Mile Rate": selected_lowest["Rate"],
                        "Total Cost": gtotal,
                        "Total per cbm": tot_pcbm
                    }
                except Exception as e:
                    errors.append(f"❌ Error processing P2P row for {destination_name}: {e}")

    return results, errors, skipped_fba
