import csv
import os
import random

def main():
    data_dir = r"c:\Users\NIRJHAR BARMA\Desktop\batcave\demo-case-data"
    
    # Read the generated people
    nodes_path = os.path.join(data_dir, "01_entities_nodes.csv")
    people_by_city = {}
    with open(nodes_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["entity_id"].startswith("P1") and row["sub_network"] == "SN-D":
                city = row["location_city"]
                if city not in people_by_city:
                    people_by_city[city] = []
                people_by_city[city].append(row["entity_id"])
    
    # City coordinates
    coords = {
        "Delhi": ("28.7041", "77.1025", "Delhi"),
        "Mumbai": ("19.0760", "72.8777", "Maharashtra"),
        "Bengaluru": ("12.9716", "77.5946", "Karnataka"),
        "Jaipur": ("26.9124", "75.7873", "Rajasthan"),
        "Patna": ("25.5941", "85.1376", "Bihar"),
        "Noida": ("28.5355", "77.3910", "UP"),
        "Gurgaon": ("28.4595", "77.0266", "Haryana")
    }

    geo_path = os.path.join(data_dir, "08_geo_locations.csv")
    locs = []
    loc_id_counter = 100
    
    # Bundle people into locations (max 50 people per location string to avoid massive cells, or just one big cell)
    # The backend splits by ";"
    for city, people in people_by_city.items():
        if city not in coords:
            continue
        lat, lon, state = coords[city]
        
        # split into chunks of 100
        chunk_size = 100
        for i in range(0, len(people), chunk_size):
            chunk = people[i:i+chunk_size]
            locs.append({
                "location_id": f"LOC{loc_id_counter}",
                "location_name": f"{city} NCIC Safehouse {i//chunk_size + 1}",
                "city": city,
                "state": state,
                "country": "India",
                "latitude": str(float(lat) + random.uniform(-0.05, 0.05)),
                "longitude": str(float(lon) + random.uniform(-0.05, 0.05)),
                "location_type": "OPERATIONAL_BASE",
                "linked_entity_ids": ";".join(chunk),
                "sub_network": "SN-D",
                "event_count": str(len(chunk) * 2),
                "notes": "1000 Crore NCIC Bust Location"
            })
            loc_id_counter += 1

    with open(geo_path, "a", newline="", encoding="utf-8") as f:
        # read headers from existing file
        writer = csv.DictWriter(f, fieldnames=["location_id","location_name","city","state","country","latitude","longitude","location_type","linked_entity_ids","sub_network","event_count","notes"])
        for loc in locs:
            writer.writerow(loc)
            
    print(f"Added {len(locs)} new locations to map.")

if __name__ == "__main__":
    main()
