# Standards data foundation

The JSON files in this directory are the small, manually curated demo corpus for
the four initial procurement domains: structural steel, pipes, electrical
installations and PPE. They contain catalogue metadata only; they do not
reproduce copyrighted standard text.

`standards.json` is the source corpus. `relationships.json` and
`certification_rules.json` are the manually verified enrichment tables. Run
`python scripts/ingest.py` to validate the source and rebuild the local
database and derived projections.
