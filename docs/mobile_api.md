Mobile API Quickstart
=====================

Auth
----
- Obtain access/refresh: `POST /api/auth/token/` with `{"username": "...", "password": "..."}`.
- Refresh: `POST /api/auth/token/refresh/` with `{"refresh": "<refresh>"}`.
- Send `Authorization: Bearer <access>` on every request.

CORS
----
Allowed localhost origins are preconfigured (`3000`, `5173`). Add your mobile/web origin in `CORS_ALLOWED_ORIGINS` for production.

Tree data (mobile-friendly)
---------------------------
- Full tree: `GET /api/families/{family_id}/tree/`
- Scoped tree: `GET /api/families/{family_id}/tree/?person_id=me&depth_up=3&depth_down=3&include_spouses=1`
  - `person_id=me` centers on the caller’s linked person.
  - `depth_up`, `depth_down` limit generations; omit to get the full tree.

Line export (maternal/paternal)
-------------------------------
- `GET /api/families/{family_id}/export/line/?person_id=me&line=maternal|paternal&mode=line|subtree&include_spouses=1&parent_hint_id=<id>&depth_up=3&depth_down=2`
- Returns `nodes`, `links`, `parentChildLinks`, `spouseLinks` plus metadata and absolute `photoUrl`/`photoThumb`.

Create a new space from a line
------------------------------
- `POST /api/families/{family_id}/export/line/create-space/`
  - Body: `{ "name": "...", "description": "...", "person_id": 123, "line": "maternal", "mode": "subtree", "include_spouses": true, "parent_hint_id": 999, "depth_up": 3, "depth_down": 2 }`
  - Requires role OWNER/ADMIN/EDITOR in the source family.
  - Creates a new FamilySpace, makes the caller OWNER, copies selected persons/relationships.

Other useful endpoints
----------------------
- Person CRUD: `/api/families/{family_id}/persons/`
- Person search: `/api/families/{family_id}/persons/search/?q=...`
- Self-link/create person: `POST /api/families/{family_id}/persons/self-link/`
- Pending changes (for approvers): `/api/families/{family_id}/person-changes/`

Media
-----
`photoUrl` is absolute; add a thumbnail derivative if needed. Keep `Authorization` on image requests if your storage is protected.
