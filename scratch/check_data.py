import json

with open("data/seed_standards.json", encoding="utf-8") as f:
    seed = json.load(f)

print("Seed standards cross references:")
for s in seed["standards"]:
    for xref in s.get("cross_references", []):
        t = xref.get("relationship_type", "")
        desc = xref.get("description", "")
        tgt = xref.get("target_standard_number", "")
        if "SUPERSED" in t.upper() or "226" in tgt or "supersed" in desc.lower():
            print(f"{s['standard_number']} -> {t} {tgt} : {desc}")

with open("data/raw/standards.json", encoding="utf-8") as f:
    raw = json.load(f)

print("\nRaw standards count:", len(raw))
print("Raw numbers:", [r.get("number") for r in raw])

if "relationships.json" in open("data/raw/relationships.json", encoding="utf-8").name:
    with open("data/raw/relationships.json", encoding="utf-8") as f:
        rel = json.load(f)
    print("\nRaw relationships count:", len(rel))
    for r in rel:
        if "supersed" in r.get("relationship_type", "").lower():
            print("Raw rel superseded:", r)
