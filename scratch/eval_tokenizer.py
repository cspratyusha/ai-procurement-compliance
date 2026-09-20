import re
import json

def teammate_tokenizer(text: str) -> list[str]:
    # Teammate 1's tokenizer in app/db/bm25_index.py:
    # re.findall(r'\b[a-z0-9\-]+\b', text.lower())
    return re.findall(r'\b[a-z0-9\-]+\b', text.lower())

def our_tokenizer(text: str) -> list[str]:
    # Our tokenizer in standards-retrieval/indexing/bm25_index.py:
    # re.findall(r'[a-zA-Z0-9]+', text.lower())
    return re.findall(r'[a-zA-Z0-9]+', text.lower())

test_queries = [
    "IS 1554",
    "IS 4984:2016",
    "IS 694:2010",
    "IS 1239 (Part 1):2004",
    "IS 4984:2016/Amd 1",
    "IS 15298-2:2016",
    "IS 2062:2011",
    "IS 808:1989",
    "IS 800:2007",
    "IS 732:2019",
    "IS 2925:1984",
    "IS 15298 (Part 1):2011",
    "IS 226:1975",
    "IS 1139:1966"
]

target_corpus = [
    "IS 2062:2011 Hot Rolled Medium and High Tensile Structural Steel",
    "IS 808:1989 Dimensions for Hot Rolled Steel Beam, Column, Channel and Angle Sections",
    "IS 800:2007 General Construction in Steel - Code of Practice",
    "IS 4984:2016 High Density Polyethylene Pipes for Water Supply",
    "IS 4984:2016/Amd 1 Amendment 1 to High Density Polyethylene Pipes",
    "IS 1239 (Part 1):2004 Steel Tubes, Tubulars and Other Wrought Steel Fittings",
    "IS 694:2010 Polyvinyl Chloride Insulated Unsheathed-and Sheathed Cables",
    "IS 732:2019 Code of Practice for Electrical Wiring Installations",
    "IS 2925:1984 Specification for Industrial Safety Helmets",
    "IS 15298 (Part 1):2011 Occupational Footwear - Part 1 Test Methods",
    "IS 15298-2:2016 Personal Protective Equipment - Part 2 Safety Footwear",
    "IS 226:1975 Structural Steel (Standard Quality)",
    "IS 1139:1966 Hot Rolled Deformed Bars for Concrete Reinforcement"
]

print(f"{'Query':<25} | {'Teammate 1 Tokens':<35} | {'Our Tokens'}")
print("-" * 80)
for q in test_queries:
    t_tokens = teammate_tokenizer(q)
    o_tokens = our_tokenizer(q)
    print(f"{q:<25} | {str(t_tokens):<35} | {str(o_tokens)}")

print("\n--- Token Matching Check ---")
for q, target in zip(test_queries, target_corpus):
    t_q = set(teammate_tokenizer(q))
    t_doc = set(teammate_tokenizer(target))
    t_overlap = t_q.intersection(t_doc)

    o_q = set(our_tokenizer(q))
    o_doc = set(our_tokenizer(target))
    o_overlap = o_q.intersection(o_doc)

    t_pass = len(t_overlap) == len(t_q)
    o_pass = len(o_overlap) == len(o_q)
    print(f"Query '{q}': Teammate match={t_pass} ({t_overlap}), Ours match={o_pass} ({o_overlap})")
