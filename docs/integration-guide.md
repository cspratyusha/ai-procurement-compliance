# Integrating the standards engine with a procurement portal

A portal (GeM, CPPP, a state e-procurement system, or an internal buying
system) can use the engine in two ways:

1. **The API**: call it from the portal's own backend or frontend, and show
   the results in the portal's own screens.
2. **The embeddable widget**: add one script tag to the page where officials
   write a specification, and the engine's recommendations appear under the
   text field as they type.

Both use the same API key and return the same answers as the engine's own
screens: certification requirements with their orders, the edition in force,
amendments, and the allied standards.

The full, always-current reference is the interactive OpenAPI page the engine
serves at `/docs` (and the machine-readable schema at `/openapi.json`).

---

## 1. Get an API key

An administrator signs in, opens **Settings → API keys**, and creates a key
for the portal. The key is shown once; store it in the portal's secrets, not in
page source that the public can read. Every call made with it is recorded in
the organisation's activity trail under the key's name, and the key can be
revoked from the same screen.

Send it on every request:

```
X-API-Key: <the key>
```

What a key can do, whoever created it:

- **Engine routes only**: searching (`/retrieve`), reading standards,
  certification and amendments, checking documents (`/audit`, `/boq`). Never
  accounts, members, keys, projects or the activity trail; those need a
  person signed in, and a key gets `403`.
- **A steady rate**: 120 calls a minute per key by default
  (`API_KEY_RATE_PER_MINUTE` on the engine). Beyond it the engine answers
  `429` with a `Retry-After` header.
- **Optionally, named web addresses**: a key created with the portal's
  address (Settings, API keys, "Widget only") is refused from any other web
  page. Use this for the widget's key.

## 2. Allow the portal's origin (browser calls only)

Calls from the portal's server need nothing more. Calls from a browser (the
widget, or portal JavaScript) must come from an origin the engine allows. Add
the portal's origin to the engine's environment and restart it:

```
ALLOWED_ORIGINS=https://portal.example.gov.in,https://staging.portal.example.gov.in
```

## 3. The calls a portal needs

| Purpose | Call |
|---|---|
| Recommend standards for a description or specification | `POST /retrieve` |
| Read one standard (title, scope, status, replacement) | `GET /standards/{IS number or id}` |
| Certification needed for a standard | `GET /standards/{number}/certification` |
| Amendments and the citation to paste | `GET /standards/{number}/amendments` |
| Allied standards (references, tests, safety, installation, related products) | `GET /standards/{number}/related` |
| Check a draft tender's citations | `POST /audit` (file upload) |
| Match each line of a bill of quantities, including Excel BOQs | `POST /boq` (file upload) |
| Every product under compulsory certification, with its order | `GET /certification-rules` |
| Languages a query can be written in | `GET /languages` |

IS numbers in a path are URL-encoded: `IS 694:2010` becomes `IS%20694%3A2010`.

### Recommend standards

```http
POST /retrieve
Content-Type: application/json
X-API-Key: <the key>

{"query": "PVC insulated copper cable for indoor panel wiring", "top_k": 5}
```

`language` is optional: omit it and the engine detects the script. Queries can
be written in English, Hindi, Marathi, Bengali, Assamese, Tamil, Telugu,
Kannada, Malayalam, Gujarati, Punjabi, Odia or Urdu.

The response, trimmed to the fields a portal usually shows:

```json
{
  "confidence": "strong",
  "confidence_reason": "The top result closely matches the wording of this query.",
  "results": [
    {
      "number": "IS 694:2010",
      "title": "PVC Insulated Cables for Working Voltages up to and including 1100 V",
      "status": "active",
      "replaced_by": null,
      "withdrawn": false,
      "citation": "IS 694:2010, incorporating ...",
      "amendment_count": 3,
      "certification": {
        "scheme": "ISI",
        "status": "in_force",
        "mandatory": true,
        "qco": "Electrical Wires, Cables, Appliances and Protection Devices and Accessories (Quality Control) Order, 2003",
        "qco_url": "https://www.bis.gov.in/...",
        "explanation": "This product requires BIS Product Certification. ..."
      }
    }
  ],
  "bis_products": [
    {"product": "PVC insulated cables ...", "is_number": "IS 694", "scheme": "ISI", "status": "in_force"}
  ],
  "expanded_with": [],
  "translation": null
}
```

What each field means for the portal's screen:

- **`confidence`**: `strong`, `uncertain` or `none`. On `none` the engine has
  no standard for the request; show the results, if at all, as "nearest text
  matches, not recommendations", never as the answer.
- **`status`, `replaced_by`, `withdrawn`**: a superseded or withdrawn edition
  names the edition to cite instead. Show it; a tender citing a withdrawn
  edition specifies something that can no longer be lawfully supplied.
- **`citation`**: the text to paste into the tender, with its amendments.
- **`certification`**: `mandatory: true` only for an obligation in force.
  `status` is one of `in_force`, `deferred` (named in an order whose
  enforcement is deferred: not yet mandatory), `voluntary` (a BIS scheme exists
  but is not compulsory, such as silver hallmarking), `related_listed`,
  `checked_none`, `not_listed` and `not_verified`. Keep them apart: showing a
  deferred order as mandatory, or `not_verified` as "no certification", tells
  the official something the law does not say.
- **`bis_products`**: products named in the query that BIS lists under
  compulsory certification, even when the catalogue holds no text for the
  standard (laptops, CCTV cameras, work chairs).
- **`expanded_with`**, **`translation`**: what the engine added to the query or
  translated it to. Show them, as the engine's own screen does, so the official
  can see what was actually searched.

### Upload a draft tender or a BOQ

```http
POST /audit            (or /boq)
Content-Type: multipart/form-data
X-API-Key: <the key>

file=<the document>
```

PDF (text or scanned, read with OCR), Word (.docx), Excel (.xlsx, .xls) and
plain text are accepted, up to 10 MB. `/audit` checks every IS number the
document cites (superseded editions with their replacement, amendments not
cited, undated citations) and lists what the cited standards depend on that the
document leaves out. `/boq` matches each line item on its own terms.

## 4. The embeddable widget

For a portal that wants recommendations inside its own specification form
without building screens, add this to the page:

```html
<script
  src="https://<engine web address>/widget/standards-widget.js"
  data-api="https://<engine API address>"
  data-key="<the key>"
  data-target="#item-specification">
</script>
```

The script is served with the engine's screens (from `frontend/public/widget/`);
`data-api` is the address of the engine's API, which may be a different host.

- `data-target` is a CSS selector for the text field officials type the
  specification into (a `textarea` or `input`).
- As the official types (after a short pause), the widget shows the top
  recommendations under the field: the IS number, title, certification
  requirement, and a warning when an edition has been replaced.
- **Insert citation** appends the standard's citation text, with its
  amendments, to the field.
- Nothing is sent until the text is long enough to describe goods (12
  characters), and each pause sends one request.

A key in `data-key` can be read by anyone who opens the page. Give the widget
its own key, created with the portal's web address so no other site can use
it, and allow that address on the engine (step 2). A script outside a browser
can still send it; the engine-only scope and the rate limit bound what that
can do, and the key can be revoked from Settings at any time.

**To keep the key out of the page entirely**, leave out `data-key` and point
`data-api` at a path on the portal's own server that adds the key and passes
the call on. The portal's own sign-in then protects it. With nginx:

```nginx
location /standards-engine/ {
    # Only signed-in portal users reach this, under the portal's own rules.
    proxy_pass https://<engine API address>/;
    proxy_set_header X-API-Key "<the key>";
    proxy_set_header Origin "";
}
```

```html
<script src="https://<engine web address>/widget/standards-widget.js"
        data-api="/standards-engine"
        data-target="#item-specification"></script>
```

A working example is at `/widget/demo.html` on the engine's web address: a
plain sample form with the widget attached.

## 5. Limits and errors

- Uploads over 10 MB are refused with `413`.
- Queries over 4,000 characters are refused with `422`.
- A missing or revoked key is refused with `401`.
- A key used for an account route, or from a web address it was not issued
  for, is refused with `403`.
- A key over its rate is refused with `429`; wait the `Retry-After` seconds.
- An unsupported file type is refused with `422` and a message naming the
  supported ones.
- Errors carry a `detail` field written for the person using the portal; it is
  safe to show as it is.

## 6. What the engine does not do

- It does not issue or verify BIS licences, registrations or hallmarks. It says
  which are required and cites the order; check the supplier's licence on BIS's
  own services.
- Its record of BIS's standards is as current as its last refresh from BIS's
  standards portal; a running engine refreshes itself weekly.
- 16,656 of its 33,023 records carry the scope text of the standard (OCR of
  the published document), 2,845 new editions the scope of the edition they
  revise, and 15 a written summary, each labelled as such; the rest are
  searchable on the official number and title only, and the standard's page
  says so.
