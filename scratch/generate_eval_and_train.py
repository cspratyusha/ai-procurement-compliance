import json
from pathlib import Path

eval_set = [
    # Category: Exact Identifier Queries
    {"query_id": "eval_01", "query": "IS 2062:2011 hot rolled structural steel", "correct_id": "std_001", "difficulty": "exact_identifier"},
    {"query_id": "eval_02", "query": "IS 808:1989 dimensions for hot rolled beam channel sections", "correct_id": "std_002", "difficulty": "exact_identifier"},
    {"query_id": "eval_03", "query": "IS 800:2007 general construction in steel code of practice", "correct_id": "std_003", "difficulty": "exact_identifier"},
    {"query_id": "eval_04", "query": "IS 4984:2016 polyethylene pipes for water supply", "correct_id": "std_004", "difficulty": "exact_identifier"},
    {"query_id": "eval_05", "query": "IS 4984:2016/Amd 1 amendment 1 for polyethylene pipes", "correct_id": "std_005", "difficulty": "exact_identifier"},
    {"query_id": "eval_06", "query": "IS 1239 (Part 1):2004 steel tubes and wrought steel fittings", "correct_id": "std_006", "difficulty": "exact_identifier"},
    {"query_id": "eval_07", "query": "IS 694:2010 PVC insulated cables up to 1100 V", "correct_id": "std_007", "difficulty": "exact_identifier"},
    {"query_id": "eval_08", "query": "IS 732:2019 electrical wiring installations code of practice", "correct_id": "std_008", "difficulty": "exact_identifier"},
    {"query_id": "eval_09", "query": "IS 2925:1984 industrial safety helmets specification", "correct_id": "std_009", "difficulty": "exact_identifier"},
    {"query_id": "eval_10", "query": "IS 15298 (Part 1):2011 personal protective equipment safety footwear test methods", "correct_id": "std_010", "difficulty": "exact_identifier"},
    {"query_id": "eval_11", "query": "IS 456:2000 plain and reinforced concrete code of practice", "correct_id": "std_011", "difficulty": "exact_identifier"},
    {"query_id": "eval_12", "query": "IS 1786:2008 high strength deformed steel bars and wires for concrete reinforcement", "correct_id": "std_012", "difficulty": "exact_identifier"},
    {"query_id": "eval_13", "query": "IS 4985:2021 unplasticized PVC pipes for potable water supplies", "correct_id": "std_013", "difficulty": "exact_identifier"},
    {"query_id": "eval_14", "query": "IS 12231:1987 UPVC pipes for soil and waste discharge systems", "correct_id": "std_014", "difficulty": "exact_identifier"},
    {"query_id": "eval_15", "query": "IS 3854:1997 switches for domestic and similar purposes", "correct_id": "std_015", "difficulty": "exact_identifier"},
    {"query_id": "eval_16", "query": "IS 15298-2:2016 safety footwear requirements for commercial and industrial work", "correct_id": "std_016", "difficulty": "exact_identifier"},
    
    # Category: Technical Description / Material Grade Queries
    {"query_id": "eval_17", "query": "Fe 500D thermo mechanically treated rebar for bridge piers and civil concrete reinforcement", "correct_id": "std_012", "difficulty": "technical_description"},
    {"query_id": "eval_18", "query": "high tensile hot rolled structural steel plates and angle sections for building fabrication", "correct_id": "std_001", "difficulty": "technical_description"},
    {"query_id": "eval_19", "query": "rigid unplasticized PVC piping for drinking water distribution network and potable mains", "correct_id": "std_013", "difficulty": "technical_description"},
    {"query_id": "eval_20", "query": "low voltage fixed electrical wiring cables single core copper insulated 1100V", "correct_id": "std_007", "difficulty": "technical_description"},
    {"query_id": "eval_21", "query": "industrial head protection hard hat helmet against falling objects in construction", "correct_id": "std_009", "difficulty": "technical_description"},
    
    # Category: Supersession & Disambiguation Queries (Testing active successor ranking over superseded predecessor)
    {"query_id": "eval_22", "query": "Tender cites IS 226 structural steel plates for bridge structure — retrieve current valid active replacement standard", "correct_id": "std_001", "difficulty": "supersession_disambiguation"},
    {"query_id": "eval_23", "query": "Procurement of standard structural steel replacing legacy obsolete IS 226 standard quality", "correct_id": "std_001", "difficulty": "supersession_disambiguation"},
    {"query_id": "eval_24", "query": "Hot rolled deformed reinforcing steel bars cited under legacy IS 1139 — get current valid replacement rebar standard", "correct_id": "std_012", "difficulty": "supersession_disambiguation"}
]

train_queries = [
    {"query": "procurement of hot rolled steel plates for structural frames and columns", "correct_id": "std_001"},
    {"query": "nominal dimensions and mass properties for hot rolled steel channels and beam sections", "correct_id": "std_002"},
    {"query": "design code and erection guidelines for steel structures and trusses", "correct_id": "std_003"},
    {"query": "high density polyethylene piping for municipal water supply lines", "correct_id": "std_004"},
    {"query": "amended requirements and test procedures for PE water supply pipes", "correct_id": "std_005"},
    {"query": "welded wrought steel tubes for water gas and utility steam pipelines", "correct_id": "std_006"},
    {"query": "polyvinyl chloride insulated sheathed power distribution wire up to 1100 volts", "correct_id": "std_007"},
    {"query": "code of practice for internal electrical wiring earthing and verification", "correct_id": "std_008"},
    {"query": "safety helmets for industrial workers protecting against brain injury and impacts", "correct_id": "std_009"},
    {"query": "test methods and performance requirements for occupational protective footwear", "correct_id": "std_010"},
    {"query": "design and construction code for reinforced concrete buildings and quality control", "correct_id": "std_011"},
    {"query": "Fe 415 and Fe 500 deformed rebar wire for concrete reinforcement structures", "correct_id": "std_012"},
    {"query": "potable water distribution pipeline using rigid uPVC pipes", "correct_id": "std_013"},
    {"query": "internal building sanitary drainage stacks and soil waste discharge pipes", "correct_id": "std_014"},
    {"query": "manual domestic lighting switches for fixed wall installation up to 16A", "correct_id": "std_015"},
    {"query": "impact resistant industrial safety boots with protective steel toe caps", "correct_id": "std_016"},
    {"query": "structural steel sections E250 grade plates and angles for civil engineering", "correct_id": "std_001"},
    {"query": "standard dimensions and sectional area of I-beam and channel sections", "correct_id": "std_002"},
    {"query": "fabrication tolerances and welding inspection for structural steelwork", "correct_id": "std_003"},
    {"query": "black PE-100 high density polyethylene pipes for water transmission", "correct_id": "std_004"},
    {"query": "screwed and socketed wrought steel pipes for water conveyance", "correct_id": "std_006"},
    {"query": "domestic electric wiring multi strand copper cable 1.1 kV grade", "correct_id": "std_007"},
    {"query": "earthing and electrical equipment installation standards for substation buildings", "correct_id": "std_008"},
    {"query": "PPE head protection helmets certified under BIS quality control order", "correct_id": "std_009"},
    {"query": "compressive strength criteria and durability requirements for RCC concrete mix design", "correct_id": "std_011"},
    {"query": "corrosion resistant TMT reinforcement steel bars for marine infrastructure", "correct_id": "std_012"},
    {"query": "pressure class uPVC pipes for agricultural irrigation and drinking water", "correct_id": "std_013"},
    {"query": "plastic soil and waste discharge piping system for residential plumbing", "correct_id": "std_014"},
    {"query": "flush mounted AC rocker switches for domestic electrical control", "correct_id": "std_015"},
    {"query": "anti skid oil resistant safety footwear for factory shop floor workers", "correct_id": "std_016"},
    {"query": "active standard for structural steel superseding historical IS 226 specification", "correct_id": "std_001"},
    {"query": "high yield strength deformed bars superseding old IS 1139 hot rolled rebar", "correct_id": "std_012"}
]

# Verify zero leakage
eval_queries_set = {item["query"].strip().lower() for item in eval_set}
train_queries_set = {item["query"].strip().lower() for item in train_queries}
overlap = eval_queries_set.intersection(train_queries_set)
assert not overlap, f"Data leakage detected! Overlap: {overlap}"
print(f"Verified 0 leakage! Eval count: {len(eval_set)}, Train count: {len(train_queries)}")

# Save to destination paths
sr_data_dir = Path("app/services/standards_retrieval/data")
sr_data_dir.mkdir(parents=True, exist_ok=True)
with open(sr_data_dir / "eval_set.json", "w", encoding="utf-8") as f:
    json.dump(eval_set, f, indent=2, ensure_ascii=False)
with open(sr_data_dir / "train_queries.json", "w", encoding="utf-8") as f:
    json.dump(train_queries, f, indent=2, ensure_ascii=False)

root_data_dir = Path("data")
with open(root_data_dir / "eval_set.json", "w", encoding="utf-8") as f:
    json.dump(eval_set, f, indent=2, ensure_ascii=False)
with open(root_data_dir / "train_queries.json", "w", encoding="utf-8") as f:
    json.dump(train_queries, f, indent=2, ensure_ascii=False)

print("Saved eval_set.json and train_queries.json to all targets successfully!")
