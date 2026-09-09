"""
Geography for the real public-record corpus.

The bundled `data/samples/gazetteer.json` only covers the 30 Mumbai neighbourhoods used by the
synthetic benchmark case. Every real source speaks a different dialect of place:

  JUDGMENT  -> a court ("Supreme Court of India", "Bombay High Court") and a state party
               ("THE STATE OF BIHAR"), never a coordinate.
  NEWS      -> a feed name that carries the desk city ("Indian Express - Mumbai").
  ICIJ      -> a full postal address ("103 WALKESHWAR ROAD; 40006 MUMBAI; INDIA").
  WATCHLIST -> an ISO country code ("IN").

`locate()` maps any of those onto a point so the map lens has something to draw. Resolution is
deliberately coarse and honest: a judgment is placed at its court, not at the scene of anything,
and `precision` records which it was so the UI can say so.
"""
from __future__ import annotations

import re
from typing import Any

# --- cities: the anchor set. Keys are matched case-insensitively against free text. -------------
CITIES: dict[str, tuple[float, float]] = {
    "mumbai": (19.0760, 72.8777), "bombay": (19.0760, 72.8777), "navi mumbai": (19.0330, 73.0297),
    "thane": (19.2183, 72.9781), "new delhi": (28.6139, 77.2090), "delhi": (28.7041, 77.1025),
    "kolkata": (22.5726, 88.3639), "calcutta": (22.5726, 88.3639), "chennai": (13.0827, 80.2707),
    "madras": (13.0827, 80.2707), "bengaluru": (12.9716, 77.5946), "bangalore": (12.9716, 77.5946),
    "hyderabad": (17.3850, 78.4867), "ahmedabad": (23.0225, 72.5714), "pune": (18.5204, 73.8567),
    "surat": (21.1702, 72.8311), "jaipur": (26.9124, 75.7873), "lucknow": (26.8467, 80.9462),
    "kanpur": (26.4499, 80.3319), "nagpur": (21.1458, 79.0882), "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126), "patna": (25.5941, 85.1376), "chandigarh": (30.7333, 76.7794),
    "guwahati": (26.1445, 91.7362), "kochi": (9.9312, 76.2673), "cochin": (9.9312, 76.2673),
    "thiruvananthapuram": (8.5241, 76.9366), "trivandrum": (8.5241, 76.9366),
    "bhubaneswar": (20.2961, 85.8245), "cuttack": (20.4625, 85.8830), "ranchi": (23.3441, 85.3096),
    "raipur": (21.2514, 81.6296), "bilaspur": (22.0797, 82.1409), "dehradun": (30.3165, 78.0322),
    "nainital": (29.3919, 79.4542), "shimla": (31.1048, 77.1734), "srinagar": (34.0837, 74.7973),
    "jammu": (32.7266, 74.8570), "amritsar": (31.6340, 74.8723), "ludhiana": (30.9010, 75.8573),
    "varanasi": (25.3176, 82.9739), "prayagraj": (25.4358, 81.8463), "allahabad": (25.4358, 81.8463),
    "agra": (27.1767, 78.0081), "vadodara": (22.3072, 73.1812), "baroda": (22.3072, 73.1812),
    "rajkot": (22.3039, 70.8022), "nashik": (19.9975, 73.7898), "aurangabad": (19.8762, 75.3433),
    "coimbatore": (11.0168, 76.9558), "madurai": (9.9252, 78.1198), "visakhapatnam": (17.6868, 83.2185),
    "vijayawada": (16.5062, 80.6480), "amaravati": (16.5735, 80.3570), "mysuru": (12.2958, 76.6394),
    "mysore": (12.2958, 76.6394), "mangaluru": (12.9141, 74.8560), "panaji": (15.4909, 73.8278),
    "goa": (15.2993, 74.1240), "gurugram": (28.4595, 77.0266), "gurgaon": (28.4595, 77.0266),
    "noida": (28.5355, 77.3910), "faridabad": (28.4089, 77.3178), "ghaziabad": (28.6692, 77.4538),
    "jodhpur": (26.2389, 73.0243), "udaipur": (24.5854, 73.7125), "gwalior": (26.2183, 78.1828),
    "jabalpur": (23.1815, 79.9864), "meerut": (28.9845, 77.7064), "jamshedpur": (22.8046, 86.2029),
    "dhanbad": (23.7957, 86.4304), "siliguri": (26.7271, 88.3953), "imphal": (24.8170, 93.9368),
    "shillong": (25.5788, 91.8933), "aizawl": (23.7271, 92.7176), "agartala": (23.8315, 91.2868),
    "itanagar": (27.0844, 93.6053), "kohima": (25.6751, 94.1086), "gangtok": (27.3314, 88.6138),
    "puducherry": (11.9416, 79.8083), "pondicherry": (11.9416, 79.8083), "kozhikode": (11.2588, 75.7804),
    "thrissur": (10.5276, 76.2144), "salem": (11.6643, 78.1460), "tiruchirappalli": (10.7905, 78.7047),
    "guntur": (16.3067, 80.4365), "warangal": (17.9689, 79.5941), "solapur": (17.6599, 75.9064),
    "kolhapur": (16.7050, 74.2433), "sangli": (16.8524, 74.5815), "ajmer": (26.4499, 74.6399),
    "bikaner": (28.0229, 73.3119), "kota": (25.2138, 75.8648), "bareilly": (28.3670, 79.4304),
    "aligarh": (27.8974, 78.0880), "gorakhpur": (26.7606, 83.3732), "jhansi": (25.4484, 78.5685),
    "muzaffarpur": (26.1197, 85.3910), "gaya": (24.7955, 85.0002), "bhagalpur": (25.2425, 86.9842),
    "asansol": (23.6739, 86.9524), "durgapur": (23.5204, 87.3119), "howrah": (22.5958, 88.2636),
}

# --- states / union territories -> their capital point ------------------------------------------
STATES: dict[str, tuple[float, float]] = {
    "maharashtra": CITIES["mumbai"], "bihar": CITIES["patna"], "uttar pradesh": CITIES["lucknow"],
    "west bengal": CITIES["kolkata"], "tamil nadu": CITIES["chennai"], "karnataka": CITIES["bengaluru"],
    "telangana": CITIES["hyderabad"], "andhra pradesh": CITIES["amaravati"], "gujarat": (23.2156, 72.6369),
    "rajasthan": CITIES["jaipur"], "madhya pradesh": CITIES["bhopal"], "kerala": CITIES["thiruvananthapuram"],
    "odisha": CITIES["bhubaneswar"], "orissa": CITIES["bhubaneswar"], "punjab": CITIES["chandigarh"],
    "haryana": CITIES["chandigarh"], "jharkhand": CITIES["ranchi"], "chhattisgarh": CITIES["raipur"],
    "assam": CITIES["guwahati"], "uttarakhand": CITIES["dehradun"], "himachal pradesh": CITIES["shimla"],
    "jammu and kashmir": CITIES["srinagar"], "jammu & kashmir": CITIES["srinagar"], "ladakh": (34.1526, 77.5771),
    "goa": CITIES["panaji"], "tripura": CITIES["agartala"], "manipur": CITIES["imphal"],
    "meghalaya": CITIES["shillong"], "mizoram": CITIES["aizawl"], "nagaland": CITIES["kohima"],
    "sikkim": CITIES["gangtok"], "arunachal pradesh": CITIES["itanagar"], "delhi": CITIES["new delhi"],
    "nct of delhi": CITIES["new delhi"], "puducherry": CITIES["puducherry"], "chandigarh": CITIES["chandigarh"],
}

# --- courts -> their seat ------------------------------------------------------------------------
COURTS: dict[str, tuple[float, float]] = {
    "supreme court": CITIES["new delhi"], "bombay high court": CITIES["mumbai"],
    "delhi high court": CITIES["new delhi"], "calcutta high court": CITIES["kolkata"],
    "madras high court": CITIES["chennai"], "karnataka high court": CITIES["bengaluru"],
    "allahabad high court": CITIES["prayagraj"], "gujarat high court": (23.2156, 72.6369),
    "kerala high court": CITIES["kochi"], "punjab and haryana high court": CITIES["chandigarh"],
    "rajasthan high court": CITIES["jodhpur"], "telangana high court": CITIES["hyderabad"],
    "andhra pradesh high court": CITIES["amaravati"], "patna high court": CITIES["patna"],
    "orissa high court": CITIES["cuttack"], "jharkhand high court": CITIES["ranchi"],
    "chhattisgarh high court": CITIES["bilaspur"], "madhya pradesh high court": CITIES["jabalpur"],
    "uttarakhand high court": CITIES["nainital"], "himachal pradesh high court": CITIES["shimla"],
    "gauhati high court": CITIES["guwahati"], "sikkim high court": CITIES["gangtok"],
    "tripura high court": CITIES["agartala"], "manipur high court": CITIES["imphal"],
    "meghalaya high court": CITIES["shillong"], "jammu": CITIES["jammu"],
}

# --- country centroids: watchlists give an ISO code and nothing else ----------------------------
COUNTRIES: dict[str, tuple[str, tuple[float, float]]] = {
    "IN": ("India", (22.3511, 78.6677)), "AE": ("United Arab Emirates", (23.4241, 53.8478)),
    "PK": ("Pakistan", (30.3753, 69.3451)), "BD": ("Bangladesh", (23.6850, 90.3563)),
    "LK": ("Sri Lanka", (7.8731, 80.7718)), "NP": ("Nepal", (28.3949, 84.1240)),
    "SG": ("Singapore", (1.3521, 103.8198)), "MY": ("Malaysia", (4.2105, 101.9758)),
    "TH": ("Thailand", (15.8700, 100.9925)), "CN": ("China", (35.8617, 104.1954)),
    "HK": ("Hong Kong", (22.3193, 114.1694)), "GB": ("United Kingdom", (55.3781, -3.4360)),
    "US": ("United States", (37.0902, -95.7129)), "CH": ("Switzerland", (46.8182, 8.2275)),
    "CY": ("Cyprus", (35.1264, 33.4299)), "MU": ("Mauritius", (-20.3484, 57.5522)),
    "VG": ("British Virgin Islands", (18.4207, -64.6400)), "KY": ("Cayman Islands", (19.3133, -81.2546)),
    "PA": ("Panama", (8.5380, -80.7821)), "SC": ("Seychelles", (-4.6796, 55.4920)),
    "BS": ("Bahamas", (25.0343, -77.3963)), "JE": ("Jersey", (49.2144, -2.1313)),
    "IM": ("Isle of Man", (54.2361, -4.5481)), "LI": ("Liechtenstein", (47.1660, 9.5554)),
    "LU": ("Luxembourg", (49.8153, 6.1296)), "MT": ("Malta", (35.9375, 14.3754)),
    "AF": ("Afghanistan", (33.9391, 67.7100)), "MM": ("Myanmar", (21.9162, 95.9560)),
    "RU": ("Russia", (61.5240, 105.3188)), "TR": ("Turkey", (38.9637, 35.2433)),
    "SA": ("Saudi Arabia", (23.8859, 45.0792)), "QA": ("Qatar", (25.3548, 51.1839)),
    "OM": ("Oman", (21.5126, 55.9233)), "KW": ("Kuwait", (29.3117, 47.4818)),
    "ID": ("Indonesia", (-0.7893, 113.9213)), "PH": ("Philippines", (12.8797, 121.7740)),
    "VN": ("Vietnam", (14.0583, 108.2772)), "JP": ("Japan", (36.2048, 138.2529)),
    "KR": ("South Korea", (35.9078, 127.7669)), "AU": ("Australia", (-25.2744, 133.7751)),
    "CA": ("Canada", (56.1304, -106.3468)), "DE": ("Germany", (51.1657, 10.4515)),
    "FR": ("France", (46.2276, 2.2137)), "NL": ("Netherlands", (52.1326, 5.2913)),
    "BE": ("Belgium", (50.5039, 4.4699)), "ES": ("Spain", (40.4637, -3.7492)),
    "IT": ("Italy", (41.8719, 12.5674)), "ZA": ("South Africa", (-30.5595, 22.9375)),
    "NG": ("Nigeria", (9.0820, 8.6753)), "KE": ("Kenya", (-0.0236, 37.9062)),
    "BR": ("Brazil", (-14.2350, -51.9253)), "MX": ("Mexico", (23.6345, -102.5528)),
}

ISO2_RE = re.compile(r"^[A-Z]{2}$")
# longest-first so "new delhi" wins over "delhi", "navi mumbai" over "mumbai"
_CITY_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(c) for c in CITIES), key=len, reverse=True)) + r")\b", re.I)
_STATE_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(s) for s in STATES), key=len, reverse=True)) + r")\b", re.I)


def country_of(code: str) -> tuple[str, float, float] | None:
    """'IN' -> ('India', 22.35, 78.67). The watchlist connectors hand us bare ISO codes."""
    hit = COUNTRIES.get((code or "").strip().upper())
    return (hit[0], hit[1][0], hit[1][1]) if hit else None


def court_point(court: str) -> tuple[float, float] | None:
    """Place a judgment at the seat of the court that issued it."""
    c = (court or "").lower()
    if not c:
        return None
    for name, pt in sorted(COURTS.items(), key=lambda kv: -len(kv[0])):
        if name in c:
            return pt
    return _state_point(c) or _city_point(c)


def _city_point(text: str) -> tuple[float, float] | None:
    m = _CITY_RE.search(text or "")
    return CITIES[m.group(1).lower()] if m else None


def _state_point(text: str) -> tuple[float, float] | None:
    m = _STATE_RE.search(text or "")
    return STATES[m.group(1).lower()] if m else None


def locate(*candidates: str | None) -> dict[str, Any] | None:
    """
    Best-effort point for any free text, tried most-specific first.

    Returns {"lat", "lon", "precision", "matched"} or None. `precision` is one of
    city | state | court | country, so a caller can render "placed at the seat of the court"
    rather than implying a street address we never had.
    """
    for raw in candidates:
        if not raw:
            continue
        text = str(raw)
        if ISO2_RE.match(text.strip()):
            hit = country_of(text)
            if hit:
                return {"lat": hit[1], "lon": hit[2], "precision": "country", "matched": hit[0]}
        m = _CITY_RE.search(text)
        if m:
            lat, lon = CITIES[m.group(1).lower()]
            return {"lat": lat, "lon": lon, "precision": "city", "matched": m.group(1).title()}
        m = _STATE_RE.search(text)
        if m:
            lat, lon = STATES[m.group(1).lower()]
            return {"lat": lat, "lon": lon, "precision": "state", "matched": m.group(1).title()}
        if "court" in text.lower():
            pt = court_point(text)
            if pt:
                return {"lat": pt[0], "lon": pt[1], "precision": "court", "matched": text[:60]}
    return None
