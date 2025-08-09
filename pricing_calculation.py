import re
import pandas as pd
from heyprimo import heyprimo_api
from exfreight import exfreight_api
from jbhunt import jbhunt_api
from math import ceil

exchange_rate=88

def summarization(data):
    import pandas as pd

    # Step 1: Flatten nested dict into rows
    rows = []
    for dest, modes in data.items():
        for mode, details in modes.items():
            rows.append({
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
                "LM Rate": details.get("Selected lm", {}).get("Rate", 0.0),
                "LM Broker": details.get("Selected lm", {}).get("Service Provider", ""),
                "LM Carrier": details.get("Selected lm", {}).get("Carrier Name", ""),
                "1st Mile": details.get("Pick-Up Charges", 0.0),
                "OCC": details.get("OCC", 0.0),
                "DCC": details.get("DCC", 0.0),
                "P2P": details.get("PER CBM P2P", 0.0),
                "Documentation": details.get("Documentation", 0.0),
                "Palletization (Per Pallet)": details.get("Palletization (Per Pallet)", 0.0)
            })

    df_all = pd.DataFrame(rows)

    results = {}
    booking_counter = 1

    # Step 2: Group by FPOD and Category
    for (fpod, category), df_group in df_all.groupby(["FPOD", "Category"]):
        orows = []

        first_mile = df_group["1st Mile"].astype(float).max()
        occ = df_group["OCC"].astype(float).max()
        dcc = df_group["DCC"].astype(float).max()
        tot_cbm = df_group["CBM"].sum()
        pallets = df_group["#Pallets"].sum()
        pal_pp = df_group["Palletization (Per Pallet)"].astype(float).max()
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
            lm[fba_code]["Service Modes"] = row["Service Modes"]

        # Step 5: Charge Heads
        orows.append({
            "Charge Heads": "1St Mile",
            "Basis": "As per Vendor",
            "Basis QTY": "",
            "Charge In $": first_mile,
            "Exchange Rate (USD to INR)": exchange_rate,
            "Per CBM": first_mile,
            "Charge in INR": first_mile * exchange_rate
        })
        orows.append({
            "Charge Heads": "OCC",
            "Basis": "Flat (Per Quote)",
            "Basis QTY": "",
            "Charge In $": occ,
            "Exchange Rate (USD to INR)": exchange_rate,
            "Per CBM": occ,
            "Charge in INR": occ * exchange_rate
        })
        orows.append({
            "Charge Heads": "DCC",
            "Basis": "Flat (Per Quote)",
            "Basis QTY": "",
            "Charge In $": dcc,
            "Exchange Rate (USD to INR)": exchange_rate,
            "Per CBM": dcc,
            "Charge in INR": dcc * exchange_rate
        })

        for fpod_inner, value in P2P_dict.items():
            cal_p2p = value['Total P2P'] * value['CBM']
            orows.append({
                "Charge Heads": f"P2P({fpod_inner})",
                "Basis": "Per CBM",
                "Basis QTY": value['CBM'],
                "Charge In $": cal_p2p,
                "Exchange Rate (USD to INR)": exchange_rate,
                "Per CBM": value['Total P2P'],
                "Charge in INR": cal_p2p * exchange_rate
            })

        if "Drayage" not in lm_delivery_type:
            cal_pal_pp = pallets * pal_pp
            orows.append({
                "Charge Heads": "Palletization",
                "Basis": "Per Pallet",
                "Basis QTY": pallets,
                "Charge In $": cal_pal_pp,
                "Exchange Rate (USD to INR)": exchange_rate,
                "Per CBM": pal_pp,
                "Charge in INR": cal_pal_pp * exchange_rate
            })

        for fba_code, value in lm.items():
            lm_rate = value["Rate"]
            lm_cbm = value["CBM"]
            service_modes = value["Service Modes"]
            if value["LM Delivery Type"] == "Drayage":
                loadability = 60
                lm_rate_pcbm = float(lm_rate) / float(loadability)
                charge_lm = float(lm_rate_pcbm) * float(lm_cbm)
            else:
                if set(service_modes) == {"FTL", "FTL53"}:
                    lm_rate_pcbm = lm_rate
                    charge_lm = float(lm_rate) * float(lm_cbm)
                elif set(service_modes) == {"FTL53"}:
                    lm_rate_pcbm = lm_rate
                    charge_lm = float(lm_rate) * float(lm_cbm)
                else:
                    lm_rate_pcbm = lm_rate
                    charge_lm = lm_rate

            orows.append({
                "Charge Heads": f"Last Mile({fba_code})",
                "Basis": "Per CBM",
                "Basis QTY": lm_cbm,
                "Charge In $": charge_lm,
                "Exchange Rate (USD to INR)": exchange_rate,
                "Per CBM": lm_rate_pcbm,
                "Charge in INR": charge_lm * exchange_rate
            })

        # Final total
        output2 = pd.DataFrame(orows)
        total_row = {
            "Charge Heads": "Total",
            "Basis": "Per CBM",
            "Basis QTY": tot_cbm,
            "Charge In $": output2["Charge In $"].sum(),
            "Exchange Rate (USD to INR)": "",
            "Per CBM": output2["Charge In $"].sum() / tot_cbm if tot_cbm else 0.0,
            "Charge in INR": output2["Charge in INR"].sum()
        }
        output2 = pd.concat([output2, pd.DataFrame([total_row])], ignore_index=True)
        output2 = output2.round(2)

        # Clean output1
        output1 = df_group[[
            "Origin Address", "POL", "P2P Type", "Consolidator", "FBA / Destn Coast", "FPOD",
            "FBA / Destn", "FBA / Destn Address", "Category", "CBM", "#Pallets", "LM Delivery Type",
            "LM Broker", "LM Carrier", "LM Rate"
        ]]

        results[f"Booking {booking_counter}"] = [output1, output2]
        booking_counter += 1

    return results



def ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_city, fba_st_code, fba_zip, qty, weight):
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
        "FBA or Destination ZIP": fba_zip,
        "Num Of Pallet": qty
    })

    ef_result = exfreight_api(fpod_zip, fba_zip, weight, qty)

    # Step 2: Parse rates from API safely
    candidates = []

    if isinstance(hp_result, dict) and "Lowest Rate" in hp_result:
        candidates.append({
            "Rate": round(float(hp_result["Lowest Rate"]), 2),
            "Carrier Name": hp_result["Carrier Name"],
            "Service Provider": "HeyPrimo"
        })

    if isinstance(ef_result, dict) and "Lowest Rate" in ef_result:
        candidates.append({
            "Rate": round(float(ef_result["Lowest Rate"]), 2),
            "Carrier Name": ef_result["Carrier Name"],
            "Service Provider": "Ex-Freight"
        })

    # Step 3: Find offline Excel rates (exact match by zip + pallet count)
    try:
        offline_match = lm[
            (lm['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
            (lm['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5)) &
            (lm['No. of pallets'] == qty)
        ]

        for _, row in offline_match.iterrows():
            candidates.append({
                "Rate": round(float(row['Rate']), 2),
                "Carrier Name": row['Carrier Name'],
                "Service Provider": row["Broker"]
            })
    except Exception as e:
        print("Error matching offline Excel rate:", e)

    # Step 4: Pick the lowest rate
    if candidates:
        return min(candidates, key=lambda x: x["Rate"])
    else:
        return None
    
def ftl_rate(fpod_zip, fba_zip, qty):
    lm = pd.read_excel(r"Data/Last Mile Rates (no api).xlsx", "Last Mile Rates (no api)")
    
    # Separate FTL and FTL53 sheets
    lm_ftl = lm[lm['Delivery Type'] == "FTL"]
    lm_ftl53 = lm[lm['Delivery Type'] == "FTL53"]

    ftl_cand = []
    ftl_match = lm_ftl[
        (lm_ftl['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5))
    ]

    for _, row in ftl_match.iterrows():
        ftl_cand.append({
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'],
            "Service Provider": row["Broker"]
        })

    ftl53_cand = []
    ftl53_match = lm_ftl53[
        (lm_ftl53['FPOD ZIP'].astype(str).str.zfill(5) == str(fpod_zip).zfill(5)) &
        (lm_ftl53['FBA ZIP'].astype(str).str.zfill(5) == str(fba_zip).zfill(5))
    ]

    for _, row in ftl53_match.iterrows():
        ftl53_cand.append({
            "Rate": round(float(row['Rate']), 2),
            "Carrier Name": row['Carrier Name'],
            "Service Provider": row["Broker"]
        })

    # Safely return min if any rates were found, else None
    best_ftl = min(ftl_cand, key=lambda x: x["Rate"]) if ftl_cand else None
    best_ftl53 = min(ftl53_cand, key=lambda x: x["Rate"]) if ftl53_cand else None

    return best_ftl, best_ftl53

def rates_comparison(fpod_city, fpod_st_code, fpod_zip, fba_city, fba_st_code, fba_zip,
                     total_pallet_count, weight, category, service_modes):
    drayage = None
    ltl = None
    ftl = None
    ftl53 = None

    # Special case for HOT category
    if set(service_modes) == {"Drayage"}:
        drayage = jbhunt_api(fpod_zip, fba_zip, "20411.657")
        drayage_lowest = {
            "Rate Type": "Drayage",
            "Rate": drayage.get("Rate"),
            "Carrier Name": drayage.get("Carrier Name"),
            "Service Provider": drayage.get("Service Provider")
        }
        return None, None, None, drayage_lowest, drayage_lowest, drayage_lowest

    # --- CASE 1: ["FTL", "FTL53"] ---
    if set(service_modes) == {"FTL", "FTL53"}:
        ftl_result, ftl53_result = ftl_rate(fpod_zip, fba_zip, total_pallet_count)

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
            "Service Provider": lowest_rate_data.get("Service Provider", "")
        }
        return None, ftl_result, ftl53_result, None, lowest, selected_lowest

    # --- CASE 2: ["FTL53"] ---
    if set(service_modes) == {"FTL53"}:
        _, ftl53_result = ftl_rate(fpod_zip, fba_zip, total_pallet_count)
        if isinstance(ftl53_result, dict) and isinstance(ftl53_result.get("Rate"), (int, float)) and ftl53_result["Rate"] > 0:
            ftl53_result["Rate"] /= 48

        lowest = selected_lowest = {
            "Rate Type": "FTL53",
            "Rate": ftl53_result.get("Rate", 0.0) if isinstance(ftl53_result, dict) else 0.0,
            "Carrier Name": ftl53_result.get("Carrier Name", "") if isinstance(ftl53_result, dict) else "",
            "Service Provider": ftl53_result.get("Service Provider", "") if isinstance(ftl53_result, dict) else ""
        }
        return None, None, ftl53_result, None, lowest, selected_lowest


    # --- CASE 3: Other combinations (with LTL or more) ---
    if "LTL" in service_modes:
        ltl = ltl_rate(fpod_city, fpod_st_code, fpod_zip, fba_city, fba_st_code, fba_zip,
                       total_pallet_count, weight)

    if "FTL" in service_modes or "FTL53" in service_modes:
        ftl_result, ftl53_result = ftl_rate(fpod_zip, fba_zip, total_pallet_count)
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
            "Service Provider": valid_rates[min_mode].get("Service Provider", "")
        }
    else:
        lowest = selected_lowest = {
            "Rate Type": "N/A",
            "Rate": 0.0,
            "Carrier Name": "",
            "Service Provider": ""
        }

    return ltl, ftl, ftl53, drayage, lowest, selected_lowest


def classify_fba_code(fba_locations: pd.DataFrame, fba_code: str, quote_cbm: float, services) -> str:

    # Filter the DataFrame to the relevant FBA code
    sub_df = fba_locations[fba_locations["FBA Code"] == fba_code]
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


def rates(origin, cleaned_data, console_type, is_occ, is_dcc, des_val, shipment_scope, pickup_charges, selected_service):

    if shipment_scope == "Door-to-Door":
        if pickup_charges in [0.0, "0.0", "", None]:
            return {}, ["Pickup charges are required for Door-to-Door shipment scope."]

    # Load Excel sheets
    try:
        fba_locations = pd.read_excel(r"Data/FBA Rates.xlsx", 'FBA Locations')
        p2p = pd.read_excel(r"Data/FBA Rates.xlsx", 'P2P')
        accessorials = pd.read_excel(r"Data/FBA Rates.xlsx", 'Accessorials')
        palletization = pd.read_excel(r"Data/FBA Rates.xlsx", 'Palletization')
    except Exception as e:
        return {}, [f"❌ Failed to load one or more Excel sheets: {e}"]

    results = {}
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
                item_weight = float(item.get("totalWeight", 0.0))
                item_cbm = float(item.get("totalVolume", 0.0))

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

            if console_type == "not selected" and console_type != "both selected":
                if fpod_unloc in ['USNYC', 'USCHS']:
                    console_type = 'Own Console'
                else:
                    if 'Drayage' in services:
                        console_type = 'Own Console'
                    else:
                        console_type = 'Coload'

            try:
                ltl, ftl, ftl53, drayage, lowest, selected_lowest = rates_comparison(
                    fpod_city, fpod_st_code, fpod_zip,
                    fba_city, fba_st_code, fba_zip,
                    total_pallet_count, weight, category, services
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
                    p2ploadability = prow['Loadability']

                    if "Drayage" in services and console_type == 'Own Console':
                        oc_p2p_usd = float(oc_p2p_inr)/float(exchange_rate)
                        t_p2p = float(oc_p2p_usd)+float(of_p2p)
                        percbm_p2p = t_p2p/p2ploadability
                    else:
                        percbm_p2p = prow['Per CBM(USD)']
                   
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
                        palletization_cost = float(pal_cost) * total_pallet_count
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
                        "Total CBM": total_cbm,
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
                        "Pick-Up Charges": pickup_charges,
                        "PER CBM P2P": percbm_p2p,
                        "PER CBM P2P & Doc": percbm_p2p + doc_pcbm,
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

    return results, errors
