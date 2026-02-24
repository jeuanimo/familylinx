# Families App Documentation

## Overview

The **families** app is the core module for managing family spaces in FamilyLinx. It provides functionality for creating family groups, managing memberships with role-based access control, and inviting new members via secure email invitations.

## Architecture

```
families/
├── __init__.py
├── admin.py           # Django admin configuration (TODO)
├── apps.py            # App configuration
├── forms.py           # Django ModelForms for user input
├── models.py          # Data models (FamilySpace, Membership, Invite)
├── urls.py            # URL routing configuration
├── views.py           # View functions
└── templates/         # HTML templates (TODO)
    └── families/
        ├── family_create.html
        ├── family_detail.html
        ├── invite_create.html
        ├── invite_invalid.html
        └── no_access.html
```

## Data Models

### FamilySpace

The primary organizational unit representing a family group.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField(120) | Display name for the family space |
| `description` | TextField | Optional description |
| `created_by` | ForeignKey(User) | User who created the space |
| `created_at` | DateTimeField | Creation timestamp |
| `root_person_1_id` | BigIntegerField | Future: Tree anchor point |
| `root_person_2_id` | BigIntegerField | Future: Tree anchor point |

### Membership

Defines the relationship between users and family spaces with role-based permissions.

| Field | Type | Description |
|-------|------|-------------|
| `family` | ForeignKey(FamilySpace) | Associated family space |
| `user` | ForeignKey(User) | Member user |
| `role` | CharField(10) | Permission level |
| `joined_at` | DateTimeField | Join timestamp |

**Role Hierarchy:**

| Role | Permissions |
|------|-------------|
| OWNER | Full control, delete family, manage all settings |
| ADMIN | Manage members, create/revoke invites |
| EDITOR | Modify family tree data |
| MEMBER | View and add basic content |
| VIEWER | Read-only access |

### Invite

Email-based invitations with secure token authentication.

| Field | Type | Description |
|-------|------|-------------|
| `family` | ForeignKey(FamilySpace) | Target family space |
| `email` | EmailField | Invitee's email |
| `token` | CharField(64) | Secure URL token |
| `role` | CharField(10) | Role upon acceptance |
| `created_by` | ForeignKey(User) | Invite creator |
| `created_at` | DateTimeField | Creation timestamp |
| `expires_at` | DateTimeField | Expiration (14 days) |
| `accepted_at` | DateTimeField | Acceptance timestamp |

## URL Endpoints

| URL | View | Description | Access |
|-----|------|-------------|--------|
| `/families/create/` | `family_create` | Create new family | Authenticated |
| `/families/<id>/` | `family_detail` | View family details | Members |
| `/families/<id>/invites/new/` | `invite_create` | Create invitation | OWNER, ADMIN |
| `/families/invite/<token>/accept/` | `invite_accept` | Accept invitation | Authenticated |

## Forms

### FamilySpaceCreateForm

Creates a new family space. Fields: `name`, `description`

### InviteCreateForm

Creates a new invitation. Fields: `email`, `role`

## Security Implementation

This app follows OWASP Top 10 security guidelines:

### 1. Broken Access Control
- All views protected with `@login_required`
- Role-based access checks in views
- `unique_together` constraint prevents duplicate memberships

### 2. Cryptographic Failures
- Invite tokens generated with `secrets.token_urlsafe(32)` (256-bit entropy)
- Tokens are unique and non-editable

### 3. Injection Prevention
- All database operations use Django ORM
- No raw SQL queries
- Form validation for all user input

### 4. Insecure Design
- Server-side validation only (never trust client)
- `created_by` fields set server-side, not from form data
- `get_object_or_404` prevents information disclosure

### 5. Security Misconfiguration
- Only necessary form fields exposed
- Related fields set programmatically

### 6. Identification & Authentication
- Django's authentication system used
- Protected by `@login_required` decorator

### 7. Software Integrity
- ForeignKey with `PROTECT` prevents accidental deletions
- `update_fields` limits database updates

### 8. Logging (TODO)
- Add logging for membership changes
- Log failed access attempts

## Usage Examples

### Creating a Family Space

```python
from families.models import FamilySpace, Membership

# Create family
family = FamilySpace.objects.create(
    name="Smith Family",
    description="Our family history project",
    created_by=user
)

# Add creator as owner
Membership.objects.create(
    family=family,
    user=user,
    role=Membership.Role.OWNER
)
```

### Creating an Invitation

```python
from families.models import Invite, Membership

invite = Invite.objects.create(
    family=family,
    email="relative@example.com",
    role=Membership.Role.MEMBER,
    created_by=admin_user
)
# Token and expires_at are auto-generated

# Build invite URL
invite_url = f"/families/invite/{invite.token}/accept/"
```

### Checking Permissions

```python
from families.models import Membership

membership = Membership.objects.filter(
    family=family,
    user=request.user
).first()

if membership and membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]:
    # User can perform admin actions
    pass
```

### Accepting an Invitation

```python
from families.models import Invite, Membership
from django.utils import timezone

invite = Invite.objects.get(token=token)

if invite.is_valid:
    Membership.objects.get_or_create(
        family=invite.family,
        user=user,
        defaults={"role": invite.role}
    )
    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted_at"])
```

## Templates Required

Create the following templates in `families/templates/families/`:

### family_create.html
Form for creating a new family space.

Context: `form` (FamilySpaceCreateForm)

### family_detail.html
Display family information, members list, and invites.

Context: `family`, `membership`, `members`, `invites`

### invite_create.html
Form for creating new invitations.

Context: `family`, `form` (InviteCreateForm)

### invite_invalid.html
Error page for expired or already-accepted invites.

Context: `invite`

### no_access.html
Access denied page for non-members.

Context: `family`

## Future Enhancements

1. **Email Notifications**: Send invite emails with secure links
2. **Rate Limiting**: Prevent invite spam
3. **Audit Logging**: Track all membership changes
4. **Admin Interface**: Django admin registration
5. **API Endpoints**: REST API for mobile apps
6. **Family Tree Integration**: Connect with tree/person models

## Dependencies

- Django 5.0+
- Python 3.11+

## Testing

```bash
# Run all families app tests
python manage.py test families

# Run with coverage
coverage run --source='families' manage.py test families
coverage report
```

## Contributing

1. Follow the security guidelines in the project README.txt
2. Add docstrings to all new functions and classes
3. Write tests for new functionality
4. Update this documentation for any changes
