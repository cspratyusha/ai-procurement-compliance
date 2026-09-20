# Fixture data — READ THIS FIRST

**Every standard number, title, scope, edition, relationship, and category
below is placeholder development data. None of it has been verified against
the actual BIS catalogue.** IS numbers are drawn from real standard families
(IS 10322 luminaires, IS 16107/16106/16101/16108 LED module/test/vocabulary
standards, IS 1944 public thoroughfare lighting, IS 3043 earthing, IS
2629/4759 galvanizing/zinc coating, IS 9974 legacy HPMV luminaires, etc.) so
the fixture's *shape* is realistic, but exact part/section numbers,
editions, scope text, and every relationship between them are invented for
structural testing and **must be replaced by Teammate 1's curated data**
before this reaches anything but a developer's own machine.

Every node and every edge carries `verified: false`. `loader/fixture_loader.py`
refuses to write `verified: false` records into anything configured as
`KR_ENV=production` unless `KR_ALLOW_UNVERIFIED_IN_PRODUCTION=true` is set
explicitly — see that module for why.

## Format

`nodes.yaml`: a list of Standard records —

```yaml
- is_number: "IS 10322-5-1:2015"
  title: "..."
  scope_text: "..."
  status: active            # active | superseded | withdrawn
  edition: "2015"
  category: "LED Street Lighting"   # or null — see "category" below
  verified: false
```

`edges.yaml`: a list of relationship records —

```yaml
- type: normative_reference   # matches a key in config/schema_map.py RELATIONSHIP_TYPES
  from: "IS 10322-5-1:2015"
  to: "IS 10322-1:2014"
  verified: false
  note: "optional human comment, ignored by the loader"
```

### `from`/`to` is an absolute, documented direction — not the read-side `RelSpec.direction`

Each relationship type has one fixed real-world arrow direction, documented
in `graph/queries.py`'s module docstring and below. The loader writes
exactly `(from)-[:TYPE]->(to)`, never consulting `RelSpec.direction` (that
field is a read-traversal concept only — see `graph/queries.py`).

| type | from -> to means |
|---|---|
| `normative_reference` | referencer -> referenced |
| `test_method_for` | test-method standard -> product standard |
| `terminology_for` | vocabulary/definitions standard -> product standard |
| `safety_requirement_for` | safety standard -> product standard |
| `installation_guide_for` | product standard -> installation/design-code standard (corrected against real Teammate 1 data during integration — was guessed the other way round in Phase 1) |
| `related_product` | either direction (symmetric) |
| `superseded_by` | old edition -> new edition |
| `overlaps_scope_with` | either direction (symmetric); carries `overlap_score` |
| `belongs_to` | standard -> product category |

### `category`

Most nodes carry both a `category` property (the Postgres/property-strategy
source) and a matching `belongs_to` edge (the Neo4j/edge-strategy source),
matching the planning docs' fan-out-from-Postgres model where the two
should normally agree. **One node, `IS 8623-1:1993`, deliberately has
`category: null`** with only a `belongs_to` edge in `edges.yaml` — this is
what exercises `StandardsRepository.get_product_category`'s fallback from
the primary strategy to the secondary one (decision 4).

## The deliberately ugly cases in `street_lighting/`

| Case | Where |
|---|---|
| Reference cycle (A -> B -> A) | `IS 16107-1:2018` <-> `IS 16106:2015`, both `normative_reference`, marked `note: synthetic cycle for cycle-safety testing` |
| Dangling reference | `IS 1944-1:1970` -> `IS 99999:1999` (not a node in this fixture) |
| Reference to a withdrawn standard | `IS 1944-1:1970` -> `IS 9900:1981` (`status: withdrawn`, no successor) |
| Hub node | `IS 12063:1987` (IP Code) — referenced by five other nodes via `normative_reference` |
| Overlapping scope pair | `IS 10322-5-1:2015` vs `IS 9974:1981` — current LED-era vs legacy HPMV street-lighting luminaire standards, same category, `overlaps_scope_with` edge with `source: curated` |
| Multiple amendments + superseding edition | `IS 10322-5-1:2001` (`status: superseded`, `superseded_by: IS 10322-5-1:2015`); the current edition carries two amendments in `amendments.yaml` |

Amendments are modelled as Postgres rows only (`amendments.yaml`, loaded
into the `amendments` table), matching the planning docs — there is no
`Amendment` node in Neo4j. See INTEGRATION.md for why `EdgeType.AMENDED_BY`
exists in the contract but is unused by this fixture.

## `reinforcement_steel/`

A second, smaller domain (reinforcement steel / TMT bars) so traversal
logic is tested against more than one topology — same format, no ugly
cases deliberately seeded (the street lighting domain already covers those).
