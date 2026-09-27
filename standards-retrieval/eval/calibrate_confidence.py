"""Calibrate the confidence thresholds on the corpus actually served.

`/retrieve` judges confidence on the cross-encoder score of its top result:
at or above `_CONFIDENCE_STRONG_MIN` is 'strong', below `_CONFIDENCE_NONE_MAX`
is 'none', and the band between is 'uncertain'. Those values were set on the
30-standard development corpus. This measures where scores actually fall at
full size, for two populations:

* in scope: the held-out eval and training queries, whose right answer is a
  standard in the corpus;
* out of scope: requests no Indian Standard covers (services, software,
  travel, insurance) and plain nonsense.

"Laptop computer" is deliberately NOT in the out-of-scope set. BIS covers
laptops (IS 13252, IT equipment safety), and the full corpus holds it; the
query misses it only because no title uses the word "laptop". Calling that
out of scope would train the gate to refuse a regulated product.

Runs against a live API:

    python eval/calibrate_confidence.py            # needs the API on :8000
"""

import json
import statistics
import sys
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8000/retrieve"
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(__file__).resolve().parent / "confidence_calibration.json"

# Requests no Indian Standard specifies. Each was chosen because the thing
# procured is a service, a right or an intangible, not a product with a
# specification; a few are nonsense, the case the gate exists for.
OUT_OF_SCOPE = [
    "annual maintenance contract for accounting software",
    "hotel booking for official travel",
    "legal counsel for an arbitration case",
    "recruitment agency for contract staff",
    "social media marketing campaign",
    "event management for a two-day conference",
    "cloud hosting subscription for a website",
    "group health insurance for employees",
    "translation of documents into Hindi",
    "courier services for official letters",
    "catering for a staff canteen",
    "security guard services for an office",
    "taxi hire for field visits",
    "architectural consultancy for a new campus",
    "internal audit of financial statements",
    "training programme on leadership skills",
    "software licence for antivirus",
    "domain name registration",
    "photography services for an event",
    "air tickets for delegates",
    "background verification of employees",
    "market research survey",
    "mobile app development",
    "advertisement in national newspapers",
    "rent for office premises",
    "sonnet about the melancholy of retired racehorses",
    "a trip to the moon",
    "recipe for chocolate cake",
    "who won the cricket world cup",
    "zzzz qqqq xxxx",
    "please write my college essay",
    "tax return filing assistance",
    "wedding planning services",
    "visa application processing",
    "music streaming subscription",
]


def retrieve(query):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "top_k": 5}).encode(),
                                 headers={"Content-Type": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=120).read())
    results = data.get("results") or []
    top = results[0]["stage_scores"]["cross_encoder"] if results else -99.0
    return top, [r["id"] for r in results[:5]]


def main():
    in_scope = []
    for name in ("eval_set_full.json", "train_queries_full.json"):
        for item in json.loads((ROOT / "data" / name).read_text(encoding="utf-8")):
            top, ids = retrieve(item["query"])
            in_scope.append({"query": item["query"], "top_ce": top, "found": item["correct_id"] in ids, "set": name})
        print(f"  {name}: done", flush=True)
    out = [{"query": q, "top_ce": retrieve(q)[0]} for q in OUT_OF_SCOPE]

    OUT.write_text(json.dumps({"in_scope": in_scope, "out_of_scope": out}, indent=1), encoding="utf-8")

    def pct(values, p):
        values = sorted(values)
        return values[min(len(values) - 1, int(p / 100 * len(values)))]

    ins = [r["top_ce"] for r in in_scope]
    ins_found = [r["top_ce"] for r in in_scope if r["found"]]
    outs = [r["top_ce"] for r in out]
    print(f"\nin scope     n={len(ins)}  min {min(ins):.2f}  p1 {pct(ins, 1):.2f}  p5 {pct(ins, 5):.2f}  median {statistics.median(ins):.2f}")
    print(f"out of scope n={len(outs)}  median {statistics.median(outs):.2f}  p95 {pct(outs, 95):.2f}  max {max(outs):.2f}")
    print("\n none_max | out-of-scope declined | in-scope wrongly declined (answer was in top 5)")
    for t in (-8, -7, -6, -5, -4, -3, -2):
        declined = sum(o < t for o in outs) / len(outs)
        wrong = sum(1 for r in in_scope if r["top_ce"] < t and r["found"]) / len(in_scope)
        print(f"   {t:>5}  | {declined:>6.0%}                | {wrong:>6.1%}")
    print("\n strong_min | in-scope called strong | out-of-scope called strong")
    for t in (-2, -1, 0, 1, 2):
        strong_in = sum(i >= t for i in ins) / len(ins)
        strong_out = sum(o >= t for o in outs) / len(outs)
        print(f"   {t:>7}  | {strong_in:>6.0%}                 | {strong_out:>6.0%}")
    print("\nhighest-scoring out-of-scope queries:")
    for r in sorted(out, key=lambda r: -r["top_ce"])[:5]:
        print(f"   {r['top_ce']:6.2f}  {r['query']}")


if __name__ == "__main__":
    sys.exit(main())
