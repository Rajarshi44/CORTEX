"""Registry of dynamic entity types, properties, and visual shapes."""

ENTITY_TYPES = {
    "PERSON": {"shape": "circle", "properties": ["name", "dob", "aliases", "nationality", "gender", "address"]},
    "ORGANIZATION": {"shape": "square", "properties": ["name", "reg_number", "industry", "address"]},
    "PHONE": {"shape": "diamond", "properties": ["number", "imei", "imsi", "provider"]},
    "BANK_ACCOUNT": {"shape": "hexagon", "properties": ["acct_no", "ifsc", "bank_name"]},
    "CRYPTO_WALLET": {"shape": "cut_hexagon", "properties": ["address", "chain"]},
    "VEHICLE": {"shape": "triangle", "properties": ["plate", "make", "model", "vin"]},
    "LOCATION": {"shape": "pin", "properties": ["address", "lat", "lon"]},
    "EMAIL": {"shape": "envelope", "properties": ["address", "provider"]},
    "SOCIAL_HANDLE": {"shape": "at", "properties": ["platform", "handle", "url"]},
}

def validate_entity_properties(entity_type: str, properties: dict) -> dict:
    """Filter out properties that are not registered for the given entity type."""
    if entity_type not in ENTITY_TYPES:
        return properties
        
    allowed = set(ENTITY_TYPES[entity_type]["properties"])
    allowed.update(["name", "label", "aliases"])
    
    return {k: v for k, v in properties.items() if k in allowed}
