Line Export & Branch Cloning
============================

Endpoints
---------
- Export JSON: `GET /api/families/{family_id}/export/line/`
  - Query params:  
    - `person_id` (defaults to caller’s linked person; use `me` on the tree endpoint)  
    - `line`: `maternal|paternal` (default maternal)  
    - `mode`: `line|subtree` (subtree adds descendants of focal)  
    - `include_spouses`: `0|1` (default 1)  
    - `parent_hint_id`: choose which mother/father on the first hop (for remarriage/adoption cases)  
    - `depth_up`: limit ancestors on the chosen line (0 = only focal)  
    - `depth_down`: limit descendants (subtree mode only)
- Create new space from a line: `POST /api/families/{family_id}/export/line/create-space/`
  - Body fields mirror the export params plus: `name`, `description`.
  - Requires role OWNER/ADMIN/EDITOR in the source family.
  - Caller becomes OWNER of the new FamilySpace; persons/relationships in-scope are copied, keeping linked_user and photos.

Returned shape
--------------
Matches tree API: `nodes`, `links`, `parentChildLinks`, `spouseLinks`, plus metadata (`line`, `mode`, `depth_up`, `depth_down`, `focal_person_id`). Media URLs are absolute.

Common flows
------------
- Seed a maternal branch space:  
  `POST /api/families/2/export/line/create-space/ { "line": "maternal", "mode": "subtree", "include_spouses": true, "depth_up": 4, "name": "Maternal Line (Alice)" }`
- Quick JSON for Flutter:  
  `GET /api/families/2/export/line/?person_id=me&line=paternal&mode=line&include_spouses=0&depth_up=5`

Notes
-----
- Ancestor selection is deterministic: earliest birth year, then lowest ID; override first hop with `parent_hint_id`.
- `depth_up`/`depth_down` are generation counts from the focal (0 = none).
- Spouses are optional; include them for cleaner card rendering.
