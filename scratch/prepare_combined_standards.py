import json
import re
from datetime import date

with open("data/raw/standards.json", encoding="utf-8") as f:
    raw_stds = json.load(f)

# 6 distinct from seed:
# IS 456:2000, IS 1786:2008, IS 4985:2021, IS 12231:1987, IS 3854:1997, IS 15298-2:2016
seed_additions = [
    {
        "id": "std_011",
        "number": "IS 456:2000",
        "title": "Plain and Reinforced Concrete — Code of Practice",
        "scope": "This standard deals with the general structural use of plain and reinforced concrete in buildings and structures. It covers design principles, material quality requirements, execution, quality control, and safety factors for reinforced concrete construction.",
        "description": "Primary Indian code of practice for plain and reinforced concrete design and structural safety. Use for all reinforced concrete construction and civil infrastructure tenders.",
        "category": "structural_steel",
        "version": "2000 (Reaffirmed 2021)",
        "last_amended": "2019-07-10",
        "status": "active",
        "keywords": ["plain concrete", "reinforced concrete", "RCC", "concrete design", "IS 456", "structural safety"]
    },
    {
        "id": "std_012",
        "number": "IS 1786:2008",
        "title": "High Strength Deformed Steel Bars and Wires for Concrete Reinforcement",
        "scope": "This standard covers the requirements of deformed steel bars and wires for use as reinforcement in concrete in grades Fe 415, Fe 415D, Fe 500, Fe 500D, Fe 550, Fe 550D, and Fe 600.",
        "description": "Primary material standard for TMT reinforcement steel bars and rebar wire for concrete construction. Replaced legacy hot rolled deformed bars standard IS 1139.",
        "category": "structural_steel",
        "version": "2008 (Reaffirmed 2018)",
        "last_amended": "2020-04-15",
        "status": "active",
        "keywords": ["TMT bars", "reinforcement steel", "rebar", "Fe 500D", "Fe 415", "concrete reinforcement", "deformed bars"]
    },
    {
        "id": "std_013",
        "number": "IS 4985:2021",
        "title": "Unplasticized PVC Pipes for Potable Water Supplies",
        "scope": "This standard covers unplasticized polyvinyl chloride (uPVC) pipes intended for potable water transportation and municipal water distribution networks.",
        "description": "Use for rigid PVC drinking water pipelines, irrigation distribution, and municipal water mains.",
        "category": "plastic_pipes",
        "version": "2021",
        "last_amended": "2021-08-20",
        "status": "active",
        "keywords": ["uPVC pipe", "PVC water pipe", "potable water supply", "unplasticized PVC", "distribution pipeline"]
    },
    {
        "id": "std_014",
        "number": "IS 12231:1987",
        "title": "UPVC Pipes for Soil and Waste Discharge Systems Inside Buildings",
        "scope": "This standard specifies requirements for unplasticized polyvinyl chloride pipes used for soil and waste discharge systems (sanitary plumbing) inside buildings.",
        "description": "Standard for internal building sanitary plumbing, drainage stacks, and domestic soil and waste discharge pipes.",
        "category": "plastic_pipes",
        "version": "1987 (Reaffirmed 2019)",
        "last_amended": "2019-12-01",
        "status": "active",
        "keywords": ["soil pipe", "waste discharge", "drainage pipe", "sanitary plumbing", "uPVC plumbing", "building drainage"]
    },
    {
        "id": "std_015",
        "number": "IS 3854:1997",
        "title": "Switches for Domestic and Similar Purposes",
        "scope": "This standard applies to manually operated general purpose switches for AC only with a rated voltage not exceeding 440 V and a rated current not exceeding 63 A intended for domestic and similar fixed electrical installations.",
        "description": "Standard specification for domestic wall switches, flush switches, and electrical installation control switches.",
        "category": "electrical_installations",
        "version": "1997 (Reaffirmed 2021)",
        "last_amended": "2021-03-10",
        "status": "active",
        "keywords": ["switches", "domestic switch", "electrical switch", "wall switch", "lighting switch", "wiring accessories"]
    },
    {
        "id": "std_016",
        "number": "IS 15298-2:2016",
        "title": "Personal Protective Equipment — Part 2: Safety Footwear",
        "scope": "This standard specifies basic and additional (optional) requirements for safety footwear used for commercial and industrial work, including impact resistance, slip resistance, and thermal hazards.",
        "description": "Commercial safety boots and shoes meeting stringent industrial safety requirements with steel toe caps and slip-resistant soles.",
        "category": "ppe",
        "version": "2016 (Reaffirmed 2021)",
        "last_amended": "2021-09-15",
        "status": "active",
        "keywords": ["safety shoes", "safety footwear", "safety boots", "steel toe", "industrial footwear", "PPE"]
    },
    # Real superseded standards:
    {
        "id": "std_017",
        "number": "IS 226:1975",
        "title": "Structural Steel (Standard Quality)",
        "scope": "This standard covers the requirements for standard quality structural steel intended for use in structural work, bridges and general engineering purposes. Superseded by IS 2062.",
        "description": "Legacy specification for structural steel plates and sections. Formally superseded and replaced by IS 2062:2011; obsolete for current public procurement.",
        "category": "structural_steel",
        "version": "1975 (Withdrawn/Superseded)",
        "last_amended": "1989-01-01",
        "status": "superseded",
        "superseded_by_id": "std_001",
        "keywords": ["structural steel", "standard quality steel", "legacy steel", "IS 226", "superseded steel"]
    },
    {
        "id": "std_018",
        "number": "IS 1139:1966",
        "title": "Hot Rolled Deformed Bars for Concrete Reinforcement",
        "scope": "This standard covers requirements of hot-rolled deformed bars for concrete reinforcement. Formally superseded by IS 1786.",
        "description": "Historical specification for hot rolled deformed reinforcing bars. Formally superseded and replaced by IS 1786:2008 for all modern reinforcement applications.",
        "category": "structural_steel",
        "version": "1966 (Withdrawn/Superseded)",
        "last_amended": "1985-01-01",
        "status": "superseded",
        "superseded_by_id": "std_012",
        "keywords": ["hot rolled deformed bars", "rebar", "legacy reinforcement", "IS 1139", "superseded bars"]
    }
]

combined = raw_stds + seed_additions

print(f"Total combined standards: {len(combined)}")
from collections import Counter
cat_counts = Counter(s["category"] for s in combined)
status_counts = Counter(s["status"] for s in combined)
print("Category distribution:", dict(cat_counts))
print("Status distribution:", dict(status_counts))

# Verify schema
REQUIRED_FIELDS = {
    "id", "number", "title", "scope", "description", "category",
    "version", "last_amended", "status", "keywords",
}
ALLOWED_STATUS = {"active", "superseded"}
ID_PATTERN = re.compile(r"^std_[0-9]{3,}$")

for i, s in enumerate(combined):
    assert not (REQUIRED_FIELDS - set(s.keys())), f"Missing field in {s['id']}"
    assert ID_PATTERN.fullmatch(s["id"]), f"Invalid ID {s['id']}"
    assert s["status"] in ALLOWED_STATUS, f"Invalid status in {s['id']}"
    date.fromisoformat(s["last_amended"])

print("All combined records validated successfully!")
