Project Features Overview
=========================

Auth & Membership
-----------------
- Email/password auth via django-allauth.
- Roles per FamilySpace: OWNER, ADMIN, EDITOR, MEMBER, VIEWER (see `families/models.py:Membership`).
- JWT for mobile/API: `POST /api/auth/token/`, `/api/auth/token/refresh/` (Bearer).
- CORS enabled for app/mobile origins (configure in `config/settings.py`).

Family Spaces
-------------
- Create/manage family groups (`families/models.py:FamilySpace`).
- Membership invites and role management.
- Owners/Admins can approve pending edits, create branch spaces, and manage members.

People & Relationships
----------------------
- Person records with photos, vitals, places, and optional linked user (`families/models.py:Person`).
- Relationship types: parent-child, spouse (and ancestor helper types).
- Permissions: MEMBER can edit self/spouse/children; broader edits require EDITOR+; others go to approval.

Family Tree (Interactive & Classic)
-----------------------------------
- Interactive D3 tree (`families/templates/families/family_tree_interactive_simple.html`):
  - Center on logged-in member (`person_id=me`), search, zoom, fit, variable depths.
  - Card photos/initials, gender colors, spacing tuned for desktop/mobile.
  - Legend, ancestors/descendants depth controls, info panel.
- Classic grid view (`families/templates/families/family_tree.html`) for tabular browsing.
- Tree API: `GET /api/families/{id}/tree/?person_id=me&depth_up=&depth_down=&include_spouses=`

Line Export & Branch Cloning
----------------------------
- Export maternal/paternal line (line or subtree): `GET /api/families/{id}/export/line/` with `line`, `mode`, `depth_up`, `depth_down`, `parent_hint_id`, `include_spouses`.
- Clone a branch into a new FamilySpace: `POST /api/families/{id}/export/line/create-space/` (caller becomes OWNER of new space).

Self-Linking & Focus
--------------------
- Members can link/create their own Person: `POST /api/families/{id}/persons/self-link/`.
- Tree centers on linked person by default; `person_id` query overrides.

Pending Changes / Approval Workflow
-----------------------------------
- Non-privileged edits create `PendingPersonChange` records.
- Approvers review via `GET/POST /api/families/{id}/person-changes/` (approve/reject).

Memories / Living Museum
------------------------
- Memories (stories, media, reactions, comments) per person; card and timeline views (`families/templates/families/museum_person.html`).
- Media attachments, story types, featured flags.

Calendar (Birthdays & Anniversaries)
------------------------------------
- Calendar endpoint/views to surface birthdays (Person.birth_date) and wedding anniversaries (Relationship.start_date for spouses). UI links from family pages.

Merge & Linking Tools
---------------------
- Tree merge requests UI (`families/templates/families/tree_merge_request.html`) and related compare/search pages to link duplicate people across trees.

Media Handling
--------------
- Absolute `photoUrl`/`photoThumb` in API responses; photos fall back to linked user profile picture when present.
- Supports privacy flag `is_private`.

API Quick List
--------------
- Tree: `GET /api/families/{id}/tree/`
- Line export: `GET /api/families/{id}/export/line/`
- Clone branch: `POST /api/families/{id}/export/line/create-space/`
- Persons: list/create `POST /api/families/{id}/persons/`, detail/update `PATCH /api/families/{id}/persons/{pk}/`
- Person search: `GET /api/families/{id}/persons/search/?q=`
- Relationships: `GET/POST /api/families/{id}/relationships/`
- Pending changes: `GET/POST /api/families/{id}/person-changes/`
- Self link: `POST /api/families/{id}/persons/self-link/`
- Auth: `POST /api/auth/token/`, `/api/auth/token/refresh/`

Mobile Readiness
----------------
- JWT auth, CORS, absolute media URLs, depth-limited tree fetches, line exports for lightweight loads.
- Responsive tweaks in interactive tree for tablet/phone.

Where to look
-------------
- Settings/auth/CORS/JWT: `config/settings.py`, `config/urls.py`
- Models: `families/models.py`
- API views/serializers: `families/api/views.py`, `families/api/serializers.py`, `families/api/urls.py`
- Tree templates: `families/templates/families/family_tree_interactive_simple.html`, `family_tree.html`
- Memories UI: `families/templates/families/museum_person.html`
- Merge UI: `families/templates/families/tree_merge_request.html`
- Docs: `docs/mobile_api.md`, `docs/line_export.md`, this file.
