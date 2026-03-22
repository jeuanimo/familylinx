"""
Families App - Views

This module contains view functions for managing family spaces, memberships,
and invitations in the FamilyLinx application.

Views:
    - family_create: Create a new family space
    - family_detail: View family space details and members
    - invite_create: Create an invitation to join a family
    - invite_accept: Accept an invitation via secure token

Security Considerations (OWASP):
    - All views require authentication (@login_required)
    - Role-based access control on sensitive actions
    - Input validation through Django forms
    - Uses get_object_or_404 to prevent information disclosure
    - No raw SQL queries (ORM only)

Templates Required:
    - families/family_create.html
    - families/family_detail.html
    - families/invite_create.html
    - families/invite_invalid.html
    - families/no_access.html
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db import models
from django.db.models import Q, Count
from datetime import date, timedelta
from collections import deque
from .models import (
    FamilySpace, Membership, Invite, Post, Comment, Event, RSVP, Person, 
    Relationship, Album, Photo, Notification, ChatMessage, create_notification, 
    AuditLog, DeletionRequest, MemoryStory, MemoryMedia, MemoryComment, 
    MemoryReaction, MuseumShare, ChatConversation, ChatConversationParticipant,
    ChatConversationMessage, ChatMessageReadReceipt, EventReminderLog
)
from .forms import FamilySpaceCreateForm, InviteCreateForm, PostCreateForm, CommentForm, EventCreateForm, PersonForm, RelationshipForm, AlbumForm, PhotoUploadForm, ChatMessageForm, ConversationMessageForm, LifeStorySectionForm, TimeCapsuleForm
from utils.image_utils import process_cropped_image


@login_required
def family_create(request):
    """
    Handle creation of a new FamilySpace.
    
    Creates a new family space and automatically assigns the creating user
    as the OWNER with full administrative permissions.
    
    HTTP Methods:
        GET: Display the family creation form
        POST: Process form submission and create family space
    
    Access Control:
        - Requires authenticated user (@login_required)
        - Any authenticated user can create a family space
    
    Flow:
        1. User submits form with family name and optional description
        2. Form validation (Django handles CSRF, input validation)
        3. FamilySpace created with user as created_by
        4. Membership created with OWNER role
        5. Redirect to family detail page
    
    Args:
        request: Django HttpRequest object
    
    Returns:
        HttpResponse: Rendered form (GET) or redirect to detail page (POST success)
    
    Template:
        families/family_create.html
    
    Context:
        form: FamilySpaceCreateForm instance
    """
    if request.method == "POST":
        form = FamilySpaceCreateForm(request.POST)
        if form.is_valid():
            # Create family space without saving to set created_by first
            fam = form.save(commit=False)
            fam.created_by = request.user
            fam.save()
            
            # Automatically make creator the OWNER
            Membership.objects.create(
                family=fam,
                user=request.user,
                role=Membership.Role.OWNER
            )
            
            return redirect("families:family_detail", family_id=fam.id)
    else:
        form = FamilySpaceCreateForm()
    
    return render(request, "families/family_create.html", {"form": form})


@login_required
def family_detail(request, family_id):
    """
    Display detailed information about a FamilySpace.
    
    Shows family information, member list, and recent invites. Access is
    restricted to users who are members of the family space.
    
    HTTP Methods:
        GET: Display family details
    
    Access Control:
        - Requires authenticated user (@login_required)
        - User must be a member of the family space
        - Non-members see the no_access template
    
    Args:
        request: Django HttpRequest object
        family_id (int): Primary key of the FamilySpace
    
    Returns:
        HttpResponse: Rendered detail page or no_access page
    
    Template:
        families/family_detail.html (members)
        families/no_access.html (non-members)
    
    Context:
        family: FamilySpace instance
        membership: Current user's Membership instance
        invites: QuerySet of recent invites (last 20)
        members: QuerySet of all memberships with related users
    
    Security Notes:
        - Uses get_object_or_404 to prevent enumeration attacks
        - Checks membership before displaying data
        - Uses select_related to optimize queries
    """
    # Fetch family or return 404 (prevents information disclosure)
    fam = get_object_or_404(FamilySpace, id=family_id)
    
    # Check if current user is a member
    membership = Membership.objects.filter(family=fam, user=request.user).first()
    if not membership:
        # User is not a member - show access denied page
        return render(request, "families/no_access.html", {"family": fam})

    # Fetch related data for display
    # Limit invites to prevent excessive data loading
    invites = fam.invites.order_by("-created_at")[:20]
    
    # Use select_related to optimize user lookup queries
    members = fam.memberships.select_related("user").order_by("joined_at")
    
    # Fetch posts for the feed (Phase 2)
    posts = fam.posts.filter(is_hidden=False).select_related(
        "author",
        "author__profile",
    ).prefetch_related(
        "comments",
        "liked_by",
        "tagged_people",
    )
    post_form = PostCreateForm(family=fam)

    feed_scope = request.GET.get("feed", "tree")
    immediate_filter_available = membership.linked_person is not None
    immediate_person_ids = _get_immediate_family_ids(membership.linked_person)

    if feed_scope == "immediate" and immediate_person_ids:
        posts = posts.filter(
            Q(author=request.user) |
            Q(author__person_profile__id__in=immediate_person_ids) |
            Q(tagged_people__id__in=immediate_person_ids)
        ).distinct()
    elif feed_scope == "immediate":
        feed_scope = "tree"

    posts = posts.order_by("-is_pinned", "-created_at")[:50]
    
    # Fetch upcoming events (Phase 3)
    upcoming_events = fam.events.filter(start_datetime__gte=timezone.now()).order_by("start_datetime")[:5]
    
    return render(request, "families/family_detail.html", {
        "family": fam,
        "membership": membership,
        "invites": invites,
        "members": members,
        "posts": posts,
        "post_form": post_form,
        "upcoming_events": upcoming_events,
        "feed_scope": feed_scope,
        "immediate_filter_available": immediate_filter_available,
        "milestones": _build_family_milestones(fam),
    })


@login_required
def family_delete(request, family_id):
    """
    Delete a FamilySpace and all associated data.
    
    Only the OWNER can delete a family space. This permanently removes
    all persons, relationships, posts, events, photos, etc.
    
    HTTP Methods:
        GET: Display deletion confirmation page
        POST: Process deletion
    
    Access Control:
        - Requires authenticated user (@login_required)
        - User must be OWNER of the family space
    """
    fam = get_object_or_404(FamilySpace, id=family_id)
    
    # Check if current user is an owner
    membership = Membership.objects.filter(family=fam, user=request.user).first()
    if not membership or membership.role != Membership.Role.OWNER:
        messages.error(request, "Only the owner can delete this family space.")
        return redirect("home")
    
    if request.method == "POST":
        family_name = fam.name
        fam.delete()  # Django will cascade delete all related objects
        messages.success(request, f"Family space '{family_name}' has been permanently deleted.")
        return redirect("home")
    
    # Get counts for confirmation page
    from .models import Person, Relationship, Event, Photo, Album
    person_count = Person.objects.filter(family=fam).count()
    relationship_count = Relationship.objects.filter(family=fam).count()
    event_count = Event.objects.filter(family=fam).count()
    photo_count = Photo.objects.filter(album__family=fam).count()
    post_count = fam.posts.count()
    member_count = fam.memberships.count()
    
    return render(request, "families/family_delete.html", {
        "family": fam,
        "membership": membership,
        "person_count": person_count,
        "relationship_count": relationship_count,
        "event_count": event_count,
        "photo_count": photo_count,
        "post_count": post_count,
        "member_count": member_count,
    })


@login_required
def invite_create(request, family_id):
    """
    Create an invitation to join a FamilySpace.
    
    Only OWNER and ADMIN roles can create invitations. The invite includes
    a secure token for URL-based acceptance.
    
    HTTP Methods:
        GET: Display the invite creation form
        POST: Process form and create invitation
    
    Access Control:
        - Requires authenticated user (@login_required)
        - User must be OWNER or ADMIN of the family space
        - Other roles see the no_access template
    
    Flow:
        1. Verify user has OWNER or ADMIN role
        2. Display form with email and role fields
        3. On valid submission, create Invite with:
           - Target family space
           - Specified email and role
           - Auto-generated secure token
           - 14-day expiration
        4. Future: Send email notification
        5. Redirect to family detail page
    
    Args:
        request: Django HttpRequest object
        family_id (int): Primary key of the FamilySpace
    
    Returns:
        HttpResponse: Rendered form, no_access page, or redirect
    
    Template:
        families/invite_create.html (authorized)
        families/no_access.html (unauthorized)
    
    Context:
        family: FamilySpace instance
        form: InviteCreateForm instance
    
    TODO:
        - Implement email sending functionality
        - Add rate limiting to prevent invite spam
    """
    # Fetch family or return 404
    fam = get_object_or_404(FamilySpace, id=family_id)
    
    # Check user's role - only OWNER and ADMIN can create invites
    membership = Membership.objects.filter(family=fam, user=request.user).first()
    if not membership or membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        # User doesn't have permission to create invites
        return render(request, "families/no_access.html", {"family": fam})

    if request.method == "POST":
        form = InviteCreateForm(request.POST)
        if form.is_valid():
            # Create invite without saving to set additional fields
            inv = form.save(commit=False)
            inv.family = fam
            inv.created_by = request.user
            inv.expires_at = timezone.now() + timezone.timedelta(days=14)
            inv.save()  # Token is auto-generated in model save()
            
            # TODO: Send email with invite link
            # send_invite_email(inv)
            
            return redirect("families:family_detail", family_id=fam.id)
    else:
        form = InviteCreateForm()
    
    return render(request, "families/invite_create.html", {"family": fam, "form": form})


@login_required
def invite_accept(request, token):
    """
    Accept an invitation to join a FamilySpace.
    
    Validates the invite token, checks expiration, and creates a membership
    for the accepting user with the role specified in the invite.
    
    HTTP Methods:
        GET: Process invite acceptance (typically from email link)
    
    Access Control:
        - Requires authenticated user (@login_required)
        - Any authenticated user with valid token can accept
        - Invalid/expired invites show error page
    
    Flow:
        1. Look up invite by secure token
        2. Validate invite (not expired, not already accepted)
        3. Create membership with specified role (or get existing)
        4. Mark invite as accepted with timestamp
        5. Redirect to family detail page
    
    Args:
        request: Django HttpRequest object
        token (str): Secure invite token from URL
    
    Returns:
        HttpResponse: Redirect to family detail or invite_invalid page
    
    Template:
        families/invite_invalid.html (invalid/expired invite)
    
    Context (invalid invite):
        invite: Invite instance (for displaying error details)
    
    Security Notes:
        - Token lookup via get_object_or_404 prevents enumeration
        - is_valid property checks both expiration and acceptance
        - get_or_create prevents duplicate memberships
        - update_fields limits database write to necessary field
    """
    # Look up invite by token - 404 if not found
    inv = get_object_or_404(Invite, token=token)
    
    # Check if invite is still valid (not expired, not already used)
    if not inv.is_valid:
        return render(request, "families/invite_invalid.html", {"invite": inv})

    # Create membership if user doesn't already have one
    # If user is already a member, their existing role is preserved
    membership, created = Membership.objects.get_or_create(
        family=inv.family,
        user=request.user,
        defaults={"role": inv.role}
    )
    
    # Mark invite as accepted
    inv.accepted_at = timezone.now()
    inv.save(update_fields=["accepted_at"])  # Only update this field
    
    # Check for matching Person records and create auto-claim
    from .models import create_auto_claim_for_user
    claim = create_auto_claim_for_user(request.user, inv.family)
    
    if claim:
        # Redirect to claim verification page
        messages.info(request, f"Welcome! We found a potential match for you in the family tree. Please verify your identity.")
        return redirect("families:verify_identity", family_id=inv.family.id, claim_id=claim.id)
    
    return redirect("families:family_detail", family_id=inv.family.id)


# =============================================================================
# Phase 2: Social Feed Views
# =============================================================================

def _get_membership_or_deny(request, family_id):
    """
    Helper to check if user is a member of the family.
    
    Returns (family, membership) tuple or raises Http404.
    """
    family = get_object_or_404(FamilySpace, id=family_id)
    try:
        membership = Membership.objects.get(family=family, user=request.user)
        return family, membership
    except Membership.DoesNotExist:
        return None, None


def _get_immediate_family_ids(person):
    """Return a set containing the person and their immediate family."""
    if not person:
        return set()

    immediate_ids = {person.id}
    immediate_ids.update(parent.id for parent in person.parents)
    immediate_ids.update(child.id for child in person.children)
    immediate_ids.update(spouse.id for spouse in person.spouses)
    immediate_ids.update(sibling.id for sibling in person.siblings)
    return immediate_ids


def _send_email_notification(recipients, subject, message, link="", request=None):
    """
    Lightweight email helper for notifications. Fails silently so UI is never blocked.
    """
    emails = [u.email for u in recipients if getattr(u, "email", None)]
    if not emails:
        return

    body = message or subject
    if link:
        absolute_link = request.build_absolute_uri(link) if request else link
        body = f"{body}\n\nOpen: {absolute_link}"

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=None,  # use DEFAULT_FROM_EMAIL
            recipient_list=emails,
            fail_silently=True,
        )
    except Exception:
        # Fail silently; in-app notification still delivered.
        pass


def _notify_users(recipients, notification_type, title, message="", link="", family=None, actor=None, request=None):
    """
    Deliver in-app + email notifications to a list of users.
    """
    notified_users = []
    for user in recipients:
        if actor and user.id == actor.id:
            continue
        notified_users.append(user)
        create_notification(
            recipient=user,
            family=family,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
        )

    _send_email_notification(notified_users, title, message, link, request=request)


def _next_annual_date(month, day, today):
    """Return the next annual occurrence for a month/day pair."""
    try:
        occurrence = date(today.year, month, day)
    except ValueError:
        occurrence = date(today.year, 2, 28)

    if occurrence < today:
        try:
            occurrence = date(today.year + 1, month, day)
        except ValueError:
            occurrence = date(today.year + 1, 2, 28)
    return occurrence


def _build_family_milestones(family, days_ahead=45):
    """Return upcoming birthdays, anniversaries, memorials, plus custom milestones."""
    today = timezone.localdate()
    cutoff = today + timedelta(days=days_ahead)
    milestones = []

    for person in family.persons.filter(is_deleted=False).order_by("first_name", "last_name"):
        if person.birth_date and person.is_living:
            next_birthday = _next_annual_date(person.birth_date.month, person.birth_date.day, today)
            if next_birthday <= cutoff:
                milestones.append({
                    "kind": "birthday",
                    "icon": "bi-cake2",
                    "title": f"{person.full_name}'s birthday",
                    "subtitle": f"Turns {next_birthday.year - person.birth_date.year}",
                    "date": next_birthday,
                    "person": person,
                })

        if person.death_date:
            next_memorial = _next_annual_date(person.death_date.month, person.death_date.day, today)
            if next_memorial <= cutoff:
                milestones.append({
                    "kind": "memorial",
                    "icon": "bi-flower1",
                    "title": f"Memorial for {person.full_name}",
                    "subtitle": f"{next_memorial.year - person.death_date.year} year remembrance",
                    "date": next_memorial,
                    "person": person,
                })

    for rel in family.relationships.filter(
        relationship_type=Relationship.Type.SPOUSE,
        is_deleted=False,
        start_date__isnull=False,
    ).select_related("person1", "person2"):
        next_anniversary = _next_annual_date(rel.start_date.month, rel.start_date.day, today)
        if next_anniversary <= cutoff:
            milestones.append({
                "kind": "anniversary",
                "icon": "bi-heart",
                "title": f"{rel.person1.full_name} and {rel.person2.full_name}",
                "subtitle": f"{next_anniversary.year - rel.start_date.year} year anniversary",
                "date": next_anniversary,
                "relationship": rel,
            })

    # Custom milestones
    for m in family.milestones.filter(date__gte=today, date__lte=cutoff).order_by("date"):
        milestones.append({
            "kind": "custom",
            "icon": "bi-stars",
            "title": m.title,
            "subtitle": m.description[:80],
            "date": m.date,
            "person": m.person,
            "event": m.event,
            "image": m.image.url if m.image else None,
            "id": m.id,
        })

    return sorted(milestones, key=lambda item: item["date"])[:12]


def _display_name_for_user(user):
    """Return the best display name available for a user."""
    if hasattr(user, "profile"):
        return user.profile.get_display_name()
    return user.email.split("@")[0]


def _conversation_title(conversation, current_user):
    """Return the display title for a conversation."""
    if conversation.title:
        return conversation.title
    if conversation.conversation_type == ChatConversation.ConversationType.FAMILY:
        return f"{conversation.family.name} Family Chat"
    if conversation.conversation_type == ChatConversation.ConversationType.EVENT and conversation.event:
        return conversation.event.title
    if conversation.conversation_type == ChatConversation.ConversationType.BRANCH and conversation.branch_root:
        return f"{conversation.branch_root.full_name} Branch Chat"
    if conversation.conversation_type == ChatConversation.ConversationType.DIRECT:
        others = [
            p.user for p in conversation.participants.select_related("user", "user__profile")
            if p.user_id != current_user.id
        ]
        if others:
            return _display_name_for_user(others[0])
        return "Direct Message"
    return "Conversation"


def _upsert_conversation_participant(conversation, user):
    """Ensure a user is attached to a conversation."""
    participant, _ = ChatConversationParticipant.objects.get_or_create(
        conversation=conversation,
        user=user,
    )
    return participant


def _ensure_shared_conversation_participants(conversation):
    """Attach all family members to non-direct conversations."""
    if conversation.conversation_type == ChatConversation.ConversationType.DIRECT:
        return
    members = Membership.objects.filter(family=conversation.family).select_related("user")
    for membership in members:
        _upsert_conversation_participant(conversation, membership.user)


def _get_or_create_family_conversation(family, user):
    """Return the family-wide group conversation."""
    conversation, _ = ChatConversation.objects.get_or_create(
        family=family,
        conversation_type=ChatConversation.ConversationType.FAMILY,
        defaults={
            "title": f"{family.name} Family Chat",
            "created_by": user,
        },
    )
    _ensure_shared_conversation_participants(conversation)
    return conversation


def _get_or_create_direct_conversation(family, user, other_user):
    """Return a stable direct conversation for two family members."""
    user_ids = sorted([user.id, other_user.id])
    direct_key = f"{family.id}:{user_ids[0]}:{user_ids[1]}"
    conversation, _ = ChatConversation.objects.get_or_create(
        direct_key=direct_key,
        defaults={
            "family": family,
            "conversation_type": ChatConversation.ConversationType.DIRECT,
            "created_by": user,
        },
    )
    _upsert_conversation_participant(conversation, user)
    _upsert_conversation_participant(conversation, other_user)
    return conversation


def _get_or_create_branch_conversation(family, user, branch_root):
    """Return or create a branch conversation for a family person."""
    conversation, _ = ChatConversation.objects.get_or_create(
        family=family,
        conversation_type=ChatConversation.ConversationType.BRANCH,
        branch_root=branch_root,
        defaults={
            "title": f"{branch_root.full_name} Branch Chat",
            "created_by": user,
        },
    )
    _ensure_shared_conversation_participants(conversation)
    return conversation


def _get_or_create_event_conversation(family, user, event):
    """Return or create a conversation attached to an event."""
    conversation, _ = ChatConversation.objects.get_or_create(
        family=family,
        conversation_type=ChatConversation.ConversationType.EVENT,
        event=event,
        defaults={
            "title": event.title,
            "created_by": user,
        },
    )
    _ensure_shared_conversation_participants(conversation)
    return conversation


def _mark_conversation_read(conversation, user):
    """Mark all visible non-own messages in a conversation as read for a user."""
    now = timezone.now()
    unread_messages = ChatConversationMessage.objects.filter(
        conversation=conversation,
        is_deleted=False,
    ).exclude(author=user)

    for message in unread_messages:
        ChatMessageReadReceipt.objects.update_or_create(
            message=message,
            user=user,
            defaults={"read_at": now},
        )

    ChatConversationParticipant.objects.filter(
        conversation=conversation,
        user=user,
    ).update(last_read_at=now)


def _serialize_conversation_message(message, current_user):
    """Build template/json-friendly message data."""
    receipts = list(
        message.read_receipts.select_related("user", "user__profile").exclude(user=message.author)
    )
    read_by = [_display_name_for_user(receipt.user) for receipt in receipts]
    return {
        "id": message.id,
        "author_label": "You" if message.author_id == current_user.id else _display_name_for_user(message.author) if message.author else "Deleted User",
        "author_id": message.author_id,
        "content": message.content,
        "created_at": message.created_at,
        "is_own": message.author_id == current_user.id,
        "read_by": read_by,
        "read_receipt_text": f"Seen by {', '.join(read_by)}" if read_by else "",
    }


def _event_type_badge(event_type):
    """Return a badge color for event types."""
    if event_type == Event.EventType.BIRTHDAY:
        return "gold"
    if event_type == Event.EventType.REUNION:
        return "green"
    if event_type in [Event.EventType.MEMORIAL, Event.EventType.FUNERAL]:
        return "red"
    return "blue"


def _notify_event_members(event, actor, title, message, include_actor=False, request=None):
    """Send an event notification to family members."""
    recipients = [m.user for m in Membership.objects.filter(family=event.family).select_related("user")]
    _notify_users(
        recipients=recipients,
        notification_type=Notification.NotificationType.EVENT,
        title=title,
        message=message,
        link=f"/families/{event.family.id}/events/{event.id}/",
        family=event.family,
        actor=None if include_actor else actor,
        request=request,
    )


def _dispatch_due_event_reminders(family, request=None):
    """Create reminder notifications for events whose reminder window has arrived."""
    now = timezone.now()
    upcoming_events = Event.objects.filter(
        family=family,
        send_reminders=True,
        start_datetime__gte=now,
    )
    for event in upcoming_events:
        reminder_at = event.start_datetime - timedelta(days=event.reminder_days_before)
        if reminder_at > now:
            continue

        reminder_date = event.start_datetime.date()
        memberships = Membership.objects.filter(family=family).select_related("user")
        for membership in memberships:
            log, created = EventReminderLog.objects.get_or_create(
                event=event,
                user=membership.user,
                reminder_for_date=reminder_date,
            )
            if not created:
                continue
            _notify_users(
                recipients=[membership.user],
                notification_type=Notification.NotificationType.EVENT,
                title=f"Reminder: {event.title}",
                message=f"{event.get_event_type_display()} on {event.start_datetime.strftime('%B %d at %I:%M %p')}",
                link=f"/families/{family.id}/events/{event.id}/",
                family=family,
                request=request,
            )


@login_required
def post_create(request, family_id):
    """
    Create a new post in the family feed.
    
    Access Control:
        - Must be authenticated
        - Must be a member of the family (VIEWER or above)
    
    Args:
        request: Django HttpRequest
        family_id: ID of the family space
    
    Returns:
        Redirect to family detail on success
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        form = PostCreateForm(request.POST, request.FILES, family=family)
        if form.is_valid():
            post = form.save(commit=False)
            post.family = family
            post.author = request.user
            post.save()
            form.save_m2m()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                post.image.save(filename, content_file, save=True)

            recipients = [
                m.user for m in Membership.objects.filter(family=family).select_related("user")
                if m.user_id != request.user.id
            ]
            author_name = _display_name_for_user(request.user)
            snippet = post.content[:120]
            _notify_users(
                recipients=recipients,
                notification_type=Notification.NotificationType.POST,
                title=f"New post in {family.name}",
                message=f"{author_name}: {snippet}",
                link=f"/families/{family.id}/posts/{post.id}/",
                family=family,
                request=request,
            )

            return redirect("families:family_detail", family_id=family.id)

        messages.error(request, "Please add some text and check any media uploads before posting.")

    return redirect("families:family_detail", family_id=family.id)


@login_required
def post_detail(request, family_id, post_id):
    """
    View a single post with its comments.
    
    Also handles comment submission via POST.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    post = get_object_or_404(
        Post.objects.select_related("author", "author__profile").prefetch_related("liked_by", "tagged_people"),
        id=post_id,
        family=family,
        is_hidden=False,
    )
    comments = post.comments.filter(is_hidden=False).select_related("author", "author__profile")
    
    # Handle comment submission
    if request.method == "POST":
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()

            recipients = set()
            if post.author_id and post.author_id != request.user.id:
                recipients.add(post.author)
            for c in post.comments.exclude(author=request.user).select_related("author"):
                if c.author:
                    recipients.add(c.author)
            for person in post.tagged_people.all():
                if person.linked_user and person.linked_user_id != request.user.id:
                    recipients.add(person.linked_user)

            commenter_name = _display_name_for_user(request.user)
            _notify_users(
                recipients=list(recipients),
                notification_type=Notification.NotificationType.COMMENT,
                title=f"New comment on a post in {family.name}",
                message=f"{commenter_name}: {comment.content[:120]}",
                link=f"/families/{family.id}/posts/{post.id}/",
                family=family,
                request=request,
            )
            return redirect("families:post_detail", family_id=family.id, post_id=post.id)
    else:
        comment_form = CommentForm()
    
    return render(request, "families/post_detail.html", {
        "family": family,
        "membership": membership,
        "post": post,
        "comments": comments,
        "comment_form": comment_form,
    })


@login_required
def post_like_toggle(request, family_id, post_id):
    """Toggle the current user's like on a family post."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    if membership.role == Membership.Role.VIEWER:
        return redirect("families:post_detail", family_id=family.id, post_id=post_id)

    post = get_object_or_404(Post, id=post_id, family=family, is_hidden=False)
    if request.method == "POST":
        if post.liked_by.filter(id=request.user.id).exists():
            post.liked_by.remove(request.user)
        else:
            post.liked_by.add(request.user)

    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("families:family_detail", family_id=family.id)


@login_required
def post_delete(request, family_id, post_id):
    """
    Delete a post (author or admin only).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    post = get_object_or_404(Post, id=post_id, family=family)
    
    # Only author or admin/owner can delete
    can_delete = (
        post.author == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    
    if not can_delete:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        post.delete()
        return redirect("families:family_detail", family_id=family.id)
    
    return render(request, "families/post_delete.html", {
        "family": family,
        "post": post,
    })


@login_required
def post_hide(request, family_id, post_id):
    """
    Hide/unhide a post (moderation - admin only).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership or membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    post = get_object_or_404(Post, id=post_id, family=family)
    
    if request.method == "POST":
        post.is_hidden = not post.is_hidden
        post.save(update_fields=["is_hidden"])
        return redirect("families:family_detail", family_id=family.id)
    
    return redirect("families:family_detail", family_id=family.id)


@login_required
def comment_delete(request, family_id, post_id, comment_id):
    """
    Delete a comment (author or admin only).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    comment = get_object_or_404(Comment, id=comment_id, post__family=family)
    
    # Only author or admin/owner can delete
    can_delete = (
        comment.author == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    
    if can_delete and request.method == "POST":
        comment.delete()
    
    return redirect("families:post_detail", family_id=family_id, post_id=post_id)


# =============================================================================
# Phase 3: Events & Calendar Views
# =============================================================================

@login_required
def event_create(request, family_id):
    """
    Create a new event for a family.
    
    Only members (non-viewers) can create events.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot create events
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        form = EventCreateForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.family = family
            event.created_by = request.user
            event.save()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                event.image.save(filename, content_file, save=True)

            if event.notify_members:
                _notify_event_members(
                    event=event,
                    actor=request.user,
                    title=f"New {event.get_event_type_display()} in {family.name}",
                    message=f"{event.title} is scheduled for {event.start_datetime.strftime('%B %d, %Y at %I:%M %p')}",
                    request=request,
                )
            
            return redirect("families:event_detail", family_id=family.id, event_id=event.id)
    else:
        form = EventCreateForm()
    
    return render(request, "families/event_create.html", {
        "family": family,
        "membership": membership,
        "form": form,
    })


@login_required
def event_detail(request, family_id, event_id):
    """
    View event details including RSVPs.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    event = get_object_or_404(Event, id=event_id, family=family)
    _dispatch_due_event_reminders(family, request=request)
    
    # Get user's current RSVP status
    user_rsvp = RSVP.objects.filter(event=event, user=request.user).first()
    
    # Get all RSVPs grouped by status
    going = RSVP.objects.filter(event=event, status=RSVP.Status.GOING).select_related('user')
    maybe = RSVP.objects.filter(event=event, status=RSVP.Status.MAYBE).select_related('user')
    not_going = RSVP.objects.filter(event=event, status=RSVP.Status.NOT_GOING).select_related('user')
    
    return render(request, "families/event_detail.html", {
        "family": family,
        "membership": membership,
        "event": event,
        "user_rsvp": user_rsvp,
        "going": going,
        "maybe": maybe,
        "not_going": not_going,
        "event_badge": _event_type_badge(event.event_type),
    })


@login_required
def event_edit(request, family_id, event_id):
    """
    Edit an existing event.
    
    Only the creator or admin/owner can edit.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    event = get_object_or_404(Event, id=event_id, family=family)
    
    # Check edit permission
    can_edit = (
        event.created_by == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    
    if not can_edit:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        form = EventCreateForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            event = form.save()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                event.image.save(filename, content_file, save=True)

            if event.notify_members:
                _notify_event_members(
                    event=event,
                    actor=request.user,
                    title=f"{event.title} was updated",
                    message=f"{event.get_event_type_display()} details changed for {event.start_datetime.strftime('%B %d, %Y at %I:%M %p')}",
                    request=request,
                )
            
            return redirect("families:event_detail", family_id=family.id, event_id=event.id)
    else:
        form = EventCreateForm(instance=event)
    
    return render(request, "families/event_edit.html", {
        "family": family,
        "membership": membership,
        "event": event,
        "form": form,
    })


@login_required
def event_delete(request, family_id, event_id):
    """
    Delete an event.
    
    Only the creator or admin/owner can delete.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    event = get_object_or_404(Event, id=event_id, family=family)
    
    # Check delete permission
    can_delete = (
        event.created_by == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    
    if not can_delete:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        event.delete()
        return redirect("families:family_detail", family_id=family.id)
    
    return render(request, "families/event_delete.html", {
        "family": family,
        "membership": membership,
        "event": event,
    })


@login_required
def event_rsvp(request, family_id, event_id):
    """
    Update user's RSVP status for an event.
    
    Creates or updates the RSVP record.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    event = get_object_or_404(Event, id=event_id, family=family)
    
    if request.method == "POST":
        status = request.POST.get("status")
        if status in [RSVP.Status.GOING, RSVP.Status.MAYBE, RSVP.Status.NOT_GOING]:
            RSVP.objects.update_or_create(
                event=event,
                user=request.user,
                defaults={"status": status}
            )
            if event.created_by_id != request.user.id:
                create_notification(
                    recipient=event.created_by,
                    notification_type=Notification.NotificationType.EVENT,
                    title=f"RSVP update for {event.title}",
                    message=f"{request.user.email} responded: {dict(RSVP.Status.choices).get(status, status)}",
                    link=f"/families/{family.id}/events/{event.id}/",
                    family=family,
                )
    
    return redirect("families:event_detail", family_id=family.id, event_id=event.id)


@login_required
def event_list(request, family_id):
    """
    List all events for a family, with option to filter past/upcoming.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    show = request.GET.get("show", "upcoming")
    event_type = request.GET.get("type", "")
    now = timezone.now()

    _dispatch_due_event_reminders(family, request=request)

    events = Event.objects.filter(family=family)
    if show == "past":
        events = events.filter(start_datetime__lt=now).order_by('-start_datetime')
    else:
        events = events.filter(start_datetime__gte=now).order_by('start_datetime')
    if event_type:
        events = events.filter(event_type=event_type)
    
    return render(request, "families/event_list.html", {
        "family": family,
        "membership": membership,
        "events": events,
        "show": show,
        "event_type": event_type,
        "event_types": Event.EventType.choices,
        "upcoming_count": Event.objects.filter(family=family, start_datetime__gte=now).count(),
        "past_count": Event.objects.filter(family=family, start_datetime__lt=now).count(),
    })


@login_required
def family_search(request, family_id):
    """
    Search across people, posts, photos, and events within a family.

    Supports free-text search plus optional date, person, and event filters.
    The event filter is also used as a date window for related posts/photos.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    query = request.GET.get("q", "").strip()
    person_id = request.GET.get("person", "").strip()
    event_id = request.GET.get("event", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    selected_person = None
    if person_id.isdigit():
        selected_person = Person.objects.filter(
            family=family,
            is_deleted=False,
            id=person_id,
        ).first()

    selected_event = None
    if event_id.isdigit():
        selected_event = Event.objects.filter(family=family, id=event_id).first()

    effective_date_from = date_from
    effective_date_to = date_to
    if selected_event:
        effective_date_from = effective_date_from or selected_event.start_datetime.date().isoformat()
        event_end = selected_event.end_datetime.date() if selected_event.end_datetime else selected_event.start_datetime.date()
        effective_date_to = effective_date_to or event_end.isoformat()

    has_active_filters = any([query, selected_person, selected_event, effective_date_from, effective_date_to])

    people = Person.objects.filter(
        family=family,
        is_deleted=False,
    ).select_related("linked_user__profile")
    posts = Post.objects.filter(
        family=family,
        is_hidden=False,
    ).select_related(
        "author",
        "author__profile",
    ).prefetch_related(
        "tagged_people",
        "liked_by",
        "comments",
    )
    photos = Photo.objects.filter(
        album__family=family,
    ).select_related(
        "album",
        "uploaded_by",
    ).prefetch_related("tagged_people")
    events = Event.objects.filter(family=family).select_related("created_by")

    if query:
        people = people.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(maiden_name__icontains=query) |
            Q(bio__icontains=query) |
            Q(birth_place__icontains=query) |
            Q(death_place__icontains=query)
        )
        posts = posts.filter(
            Q(content__icontains=query) |
            Q(author__email__icontains=query) |
            Q(author__profile__display_name__icontains=query) |
            Q(tagged_people__first_name__icontains=query) |
            Q(tagged_people__last_name__icontains=query)
        ).distinct()
        photos = photos.filter(
            Q(caption__icontains=query) |
            Q(taken_location__icontains=query) |
            Q(album__title__icontains=query) |
            Q(tagged_people__first_name__icontains=query) |
            Q(tagged_people__last_name__icontains=query)
        ).distinct()
        events = events.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(location__icontains=query)
        )

    if selected_person:
        people = people.filter(id=selected_person.id)
        posts = posts.filter(
            Q(tagged_people=selected_person) |
            Q(author__person_profile=selected_person)
        ).distinct()
        photos = photos.filter(tagged_people=selected_person).distinct()
        events = events.filter(
            Q(title__icontains=selected_person.first_name) |
            Q(title__icontains=selected_person.last_name) |
            Q(description__icontains=selected_person.first_name) |
            Q(description__icontains=selected_person.last_name)
        ).distinct()

    if effective_date_from:
        people = people.filter(
            Q(birth_date__gte=effective_date_from) |
            Q(death_date__gte=effective_date_from)
        ).distinct()
        posts = posts.filter(created_at__date__gte=effective_date_from)
        photos = photos.filter(
            Q(taken_date__gte=effective_date_from) |
            Q(taken_date__isnull=True, uploaded_at__date__gte=effective_date_from)
        ).distinct()
        events = events.filter(start_datetime__date__gte=effective_date_from)

    if effective_date_to:
        people = people.filter(
            Q(birth_date__lte=effective_date_to) |
            Q(death_date__lte=effective_date_to)
        ).distinct()
        posts = posts.filter(created_at__date__lte=effective_date_to)
        photos = photos.filter(
            Q(taken_date__lte=effective_date_to) |
            Q(taken_date__isnull=True, uploaded_at__date__lte=effective_date_to)
        ).distinct()
        events = events.filter(start_datetime__date__lte=effective_date_to)

    if selected_event:
        events = events.filter(id=selected_event.id)

    if has_active_filters:
        people = people.order_by("last_name", "first_name")[:24]
        posts = posts.order_by("-created_at")[:18]
        photos = photos.order_by("-taken_date", "-uploaded_at")[:18]
        events = events.order_by("start_datetime")[:18]
    else:
        people = people.order_by("last_name", "first_name")[:12]
        posts = posts.order_by("-created_at")[:8]
        photos = photos.order_by("-taken_date", "-uploaded_at")[:8]
        events = events.order_by("-start_datetime")[:8]

    people_filter_options = family.persons.filter(
        is_deleted=False
    ).order_by("last_name", "first_name")
    event_filter_options = family.events.order_by("-start_datetime")[:50]

    return render(request, "families/family_search.html", {
        "family": family,
        "membership": membership,
        "query": query,
        "date_from": effective_date_from,
        "date_to": effective_date_to,
        "selected_person": selected_person,
        "selected_event": selected_event,
        "people_filter_options": people_filter_options,
        "event_filter_options": event_filter_options,
        "people_results": people,
        "post_results": posts,
        "photo_results": photos,
        "event_results": events,
        "has_active_filters": has_active_filters,
    })


# =============================================================================
# Phase 4: Family Tree Views
# =============================================================================

@login_required
def family_tree(request, family_id):
    """
    Display the family tree visualization centered on ME (logged-in user's linked person).
    
    Generations are relative to ME:
    - Negative numbers = ancestors (parents=-1, grandparents=-2, etc.)
    - 0 = ME and my generation (siblings, spouse)
    - Positive numbers = descendants (children=1, grandchildren=2, etc.)
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Get all persons and relationships
    all_persons = list(Person.objects.filter(family=family, is_deleted=False)
                       .select_related('linked_user'))
    relationships = list(Relationship.objects.filter(family=family, is_deleted=False)
                        .select_related('person1', 'person2'))
    
    # Build lookup structures
    person_by_id = {p.id: p for p in all_persons}
    
    # Build parent/child/spouse maps
    children_of = {}  # parent_id -> [child_ids]
    parents_of = {}   # child_id -> [parent_ids]
    spouses_of = {}   # person_id -> [spouse_ids]
    
    for rel in relationships:
        if rel.relationship_type == Relationship.Type.PARENT_CHILD:
            children_of.setdefault(rel.person1_id, []).append(rel.person2_id)
            parents_of.setdefault(rel.person2_id, []).append(rel.person1_id)
        elif rel.relationship_type == Relationship.Type.SPOUSE:
            spouses_of.setdefault(rel.person1_id, []).append(rel.person2_id)
            spouses_of.setdefault(rel.person2_id, []).append(rel.person1_id)
    
    # Get linked person (ME)
    linked_person_id = None
    me_person = None
    if membership.linked_person:
        linked_person_id = membership.linked_person_id
        me_person = person_by_id.get(linked_person_id)
    
    # If user has a linked person, build tree centered on them
    # For static view: ONLY show direct lineage (ancestors, descendants, their spouses)
    # This removes siblings, cousins, aunts/uncles, etc.
    if me_person:
        direct_lineage_ids = set()
        direct_lineage_ids.add(me_person.id)
        
        # Add ME's spouse(s)
        for spouse_id in spouses_of.get(me_person.id, []):
            direct_lineage_ids.add(spouse_id)
        
        # Trace direct ancestors UP (parents, grandparents, etc.)
        ancestors_to_process = list(parents_of.get(me_person.id, []))
        while ancestors_to_process:
            ancestor_id = ancestors_to_process.pop(0)
            if ancestor_id in direct_lineage_ids:
                continue
            direct_lineage_ids.add(ancestor_id)
            # Add ancestor's spouse (to show both parents/grandparents)
            for spouse_id in spouses_of.get(ancestor_id, []):
                if spouse_id not in direct_lineage_ids:
                    direct_lineage_ids.add(spouse_id)
                    # Include that spouse's parents too (full lineage)
                    ancestors_to_process.extend(parents_of.get(spouse_id, []))
            # Continue up to next generation
            ancestors_to_process.extend(parents_of.get(ancestor_id, []))
        
        # Trace direct descendants DOWN (children, grandchildren, etc.)
        descendants_to_process = list(children_of.get(me_person.id, []))
        # Also include children from spouse
        for spouse_id in spouses_of.get(me_person.id, []):
            descendants_to_process.extend(children_of.get(spouse_id, []))
        
        while descendants_to_process:
            desc_id = descendants_to_process.pop(0)
            if desc_id in direct_lineage_ids:
                continue
            direct_lineage_ids.add(desc_id)
            # Add descendant's spouse
            for spouse_id in spouses_of.get(desc_id, []):
                if spouse_id not in direct_lineage_ids:
                    direct_lineage_ids.add(spouse_id)
            # Continue down to next generation
            descendants_to_process.extend(children_of.get(desc_id, []))
        
        # Filter to only direct lineage
        persons = [p for p in all_persons if p.id in direct_lineage_ids]
        
        # Assign generations relative to ME using BFS
        # ME = generation 0, parents = -1, children = +1, etc.
        generation = {me_person.id: 0}
        gen_queue = deque([me_person.id])
        processed = set()
        
        while gen_queue:
            pid = gen_queue.popleft()
            if pid in processed:
                continue
            processed.add(pid)
            my_gen = generation[pid]
            
            # Parents are one generation above (lower number)
            for parent_id in parents_of.get(pid, []):
                if parent_id in direct_lineage_ids and parent_id not in generation:
                    generation[parent_id] = my_gen - 1
                    gen_queue.append(parent_id)
            
            # Children are one generation below (higher number)
            for child_id in children_of.get(pid, []):
                if child_id in direct_lineage_ids and child_id not in generation:
                    generation[child_id] = my_gen + 1
                    gen_queue.append(child_id)
            
            # Spouses are same generation
            for spouse_id in spouses_of.get(pid, []):
                if spouse_id in direct_lineage_ids and spouse_id not in generation:
                    generation[spouse_id] = my_gen
                    gen_queue.append(spouse_id)
        
        # Normalize spouse generations (they must match)
        changed = True
        iterations = 0
        while changed and iterations < 20:
            changed = False
            iterations += 1
            for pid, spouse_ids in spouses_of.items():
                if pid not in generation:
                    continue
                for spouse_id in spouse_ids:
                    if spouse_id in generation:
                        if generation[pid] != generation[spouse_id]:
                            # Use the max (further from ancestors)
                            max_gen = max(generation[pid], generation[spouse_id])
                            if generation[pid] != max_gen or generation[spouse_id] != max_gen:
                                generation[pid] = max_gen
                                generation[spouse_id] = max_gen
                                changed = True
            
            # Ensure children are always below parents
            for parent_id, child_ids in children_of.items():
                if parent_id not in generation:
                    continue
                parent_gen = generation[parent_id]
                for child_id in child_ids:
                    if child_id in generation and generation[child_id] <= parent_gen:
                        generation[child_id] = parent_gen + 1
                        changed = True
    else:
        # No linked person - show all persons with generation 0
        persons = all_persons
        generation = {p.id: 0 for p in persons}
    
    # Handle any persons without generation assignment
    for p in persons:
        if p.id not in generation:
            generation[p.id] = 0
    
    # Group persons by generation
    generations_dict = {}
    for p in persons:
        gen = generation.get(p.id, 0)
        generations_dict.setdefault(gen, []).append(p)
    
    # Build tree structure with proper labels
    # Sort by generation number (lowest/most negative first = oldest ancestors)
    tree_generations = []
    seen_ids = set()
    unit_order = {}
    
    for gen_num in sorted(generations_dict.keys()):
        gen_persons = generations_dict[gen_num]
        gen_units = []
        
        # Sort persons within generation
        def get_sort_key(p):
            # Linked person (ME) should be first in their generation
            if p.id == linked_person_id:
                return (0, 0, p.first_name)
            # Then sort by parent position, then birth year
            parent_ids = parents_of.get(p.id, [])
            if parent_ids:
                orders = [unit_order.get(pid, 9999) for pid in parent_ids]
                return (1, min(orders), p.birth_date.year if p.birth_date else 9999)
            return (2, 9999, p.birth_date.year if p.birth_date else 9999)
        
        gen_persons_sorted = sorted(gen_persons, key=get_sort_key)
        
        for p in gen_persons_sorted:
            if p.id in seen_ids:
                continue
            seen_ids.add(p.id)
            
            # Build unit with spouse
            unit = {
                'persons': [p],
                'children_ids': set(children_of.get(p.id, [])),
            }
            
            # Add spouse(s)
            for spouse_id in spouses_of.get(p.id, []):
                if spouse_id not in seen_ids:
                    spouse = person_by_id.get(spouse_id)
                    if spouse and spouse.id in generation and generation[spouse.id] == gen_num:
                        unit['persons'].append(spouse)
                        unit['children_ids'].update(children_of.get(spouse_id, []))
                        seen_ids.add(spouse_id)
            
            gen_units.append(unit)
        
        # Assign order for child positioning
        for idx, unit in enumerate(gen_units):
            for person in unit['persons']:
                unit_order[person.id] = idx
        
        # Create generation label
        if gen_num < 0:
            if gen_num == -1:
                label = "Parents"
            elif gen_num == -2:
                label = "Grandparents"
            elif gen_num == -3:
                label = "Great-Grandparents"
            else:
                prefix = "Great-" * (abs(gen_num) - 2)
                label = f"{prefix}Grandparents"
        elif gen_num == 0:
            label = "Me & My Generation"
        elif gen_num == 1:
            label = "Children"
        elif gen_num == 2:
            label = "Grandchildren"
        elif gen_num == 3:
            label = "Great-Grandchildren"
        else:
            prefix = "Great-" * (gen_num - 2)
            label = f"{prefix}Grandchildren"
        
        tree_generations.append({
            'generation': gen_num,
            'label': label,
            'units': gen_units,
        })
    
    return render(request, "families/family_tree.html", {
        "family": family,
        "membership": membership,
        "persons": persons,
        "all_persons": all_persons,
        "relationships": relationships,
        "tree_generations": tree_generations,
        "spouses_of": spouses_of,
        "children_of": children_of,
        "parents_of": parents_of,
        "linked_person_id": linked_person_id,
        "has_linked_person": me_person is not None,
    })


@login_required
def family_tree_data(request, family_id):
    """
    Return family tree data as JSON for visualization.
    
    Returns nodes (persons) and edges (relationships) in a format
    suitable for tree visualization libraries.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    # Filter out deleted records
    persons = Person.objects.filter(family=family, is_deleted=False)
    relationships = Relationship.objects.filter(family=family, is_deleted=False)
    
    nodes = []
    for p in persons:
        nodes.append({
            "id": p.id,
            "name": p.full_name,
            "gender": p.gender,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
            "death_date": p.death_date.isoformat() if p.death_date else None,
            "is_living": p.is_living,
            "photo": p.photo.url if p.photo else None,
        })
    
    edges = []
    for r in relationships:
        edges.append({
            "source": r.person1_id,
            "target": r.person2_id,
            "type": r.relationship_type,
        })
    
    return JsonResponse({"nodes": nodes, "edges": edges})


@login_required
def family_tree_interactive(request, family_id):
    """
    Display the interactive D3.js family tree.
    
    Uses the REST API to fetch data and renders an interactive
    tree with zoom, pan, and click-to-select functionality.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    can_edit = membership.role in ['OWNER', 'ADMIN', 'EDITOR']
    
    # Get user's linked person for centering the tree
    linked_person_id = None
    if membership.linked_person:
        linked_person_id = membership.linked_person.id
    else:
        # Also check profile's linked_person
        try:
            profile = request.user.profile
            if profile.linked_person and profile.linked_person.family_id == family.id:
                linked_person_id = profile.linked_person.id
                # Sync to membership
                membership.linked_person = profile.linked_person
                membership.save()
        except Exception:
            pass
    
    return render(request, "families/family_tree_interactive.html", {
        "family": family,
        "membership": membership,
        "can_edit": can_edit,
        "linked_person_id": linked_person_id,
    })


@login_required
def link_to_tree(request, family_id):
    """
    Link the current user to a Person record in the family tree.
    
    GET: Returns JSON list of persons for search/selection.
    POST: Links the user's membership to a selected person.
    DELETE: Removes the link.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    if request.method == "GET":
        # Search for persons
        search = request.GET.get('q', '').strip()
        persons = Person.objects.filter(family=family).order_by('last_name', 'first_name')
        
        if search:
            from django.db.models import Q
            persons = persons.filter(
                Q(first_name__icontains=search) | 
                Q(last_name__icontains=search)
            )
        
        # Return list with current linked status
        data = {
            "linked_person_id": membership.linked_person_id,
            "persons": [
                {
                    "id": p.id,
                    "name": f"{p.first_name} {p.last_name}".strip(),
                    "birth_year": p.birth_date.year if p.birth_date else None,
                    "is_linked": p.id == membership.linked_person_id,
                }
                for p in persons[:50]  # Limit results
            ]
        }
        return JsonResponse(data)
    
    elif request.method == "POST":
        import json
        try:
            data = json.loads(request.body)
            person_id = data.get('person_id')
            
            if person_id:
                person = get_object_or_404(Person, id=person_id, family=family)
                membership.linked_person = person
                membership.save()
                return JsonResponse({
                    "success": True, 
                    "message": f"Linked to {person.first_name} {person.last_name}",
                    "person_id": person.id,
                    "person_name": f"{person.first_name} {person.last_name}".strip()
                })
            else:
                # Unlink
                membership.linked_person = None
                membership.save()
                return JsonResponse({"success": True, "message": "Unlinked from tree"})
                
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
def find_my_match(request, family_id):
    """
    Find potential Person matches for the current user in the family tree.
    
    Shows all potential matches and lets the user claim one.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Check if already linked via membership
    if membership.linked_person:
        messages.info(request, f"You are already linked to {membership.linked_person}")
        return redirect("families:family_tree_interactive", family_id=family.id)
    
    # Also check if linked via user profile (and sync if so)
    try:
        profile = request.user.profile
        if profile.linked_person and profile.linked_person.family_id == family.id:
            # Sync profile link to membership
            membership.linked_person = profile.linked_person
            membership.save()
            messages.info(request, f"You are already linked to {profile.linked_person}")
            return redirect("families:family_tree_interactive", family_id=family.id)
    except Exception:
        pass
    
    from .models import find_matching_persons, PersonClaim
    
    # Find potential matches
    matches = find_matching_persons(request.user, family)
    
    # Get existing claims for this user in this family
    existing_claims = PersonClaim.objects.filter(
        user=request.user,
        family=family
    ).select_related('person')
    
    return render(request, "families/find_my_match.html", {
        "family": family,
        "membership": membership,
        "matches": matches,
        "existing_claims": existing_claims,
    })


@login_required
def claim_identity(request, family_id, person_id):
    """
    Start the identity claim process for a specific Person.
    
    Creates a PersonClaim and redirects to verification.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    person = get_object_or_404(Person, id=person_id, family=family)
    
    from .models import PersonClaim, find_matching_persons
    
    # Check if already linked
    if membership.linked_person:
        messages.warning(request, "You are already linked to a person in this tree.")
        return redirect("families:family_tree_interactive", family_id=family.id)
    
    # Check if person is already claimed by someone else
    existing_verified = PersonClaim.objects.filter(
        person=person,
        status=PersonClaim.Status.VERIFIED
    ).exclude(user=request.user).exists()
    
    if existing_verified:
        messages.error(request, "This person has already been claimed by another user.")
        return redirect("families:find_my_match", family_id=family.id)
    
    # Calculate match score
    matches = find_matching_persons(request.user, family)
    match_score = 0.0
    for p, score in matches:
        if p.id == person.id:
            match_score = score
            break
    
    # Create or get existing claim
    claim, created = PersonClaim.objects.get_or_create(
        user=request.user,
        person=person,
        family=family,
        defaults={
            'name_match_score': match_score,
            'auto_matched': False,
        }
    )
    
    return redirect("families:verify_identity", family_id=family.id, claim_id=claim.id)


@login_required
def verify_identity(request, family_id, claim_id):
    """
    Verify identity by providing personal information that matches the Person record.
    
    User provides birth date, parents' names, etc. to prove they are who they claim.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import PersonClaim, Relationship
    
    claim = get_object_or_404(PersonClaim, id=claim_id, user=request.user, family=family)
    person = claim.person
    
    # Get person's parents for hint display
    parent_rels = Relationship.objects.filter(
        person2=person,
        relationship_type=Relationship.Type.PARENT_CHILD
    ).select_related('person1')
    
    father = None
    mother = None
    for rel in parent_rels:
        if rel.person1.gender == Person.Gender.MALE:
            father = rel.person1
        elif rel.person1.gender == Person.Gender.FEMALE:
            mother = rel.person1
    
    if request.method == "POST":
        # Get submitted data
        birth_date_str = request.POST.get('birth_date', '')
        birth_place = request.POST.get('birth_place', '').strip()
        father_name = request.POST.get('father_name', '').strip()
        mother_name = request.POST.get('mother_name', '').strip()
        
        # Parse birth date
        birth_date = None
        if birth_date_str:
            try:
                from datetime import datetime
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        # Update claim with provided data
        claim.provided_birth_date = birth_date
        claim.provided_birth_place = birth_place
        claim.provided_father_name = father_name
        claim.provided_mother_name = mother_name
        claim.save()
        
        # Try auto-verify
        if claim.auto_verify_if_strong_match():
            messages.success(request, f"Identity verified! You are now linked to {person} in the family tree.")
            return redirect("families:family_tree_interactive", family_id=family.id)
        
        # Calculate score and show result
        score = claim.calculate_verification_score()
        
        if score >= 0.7:
            # Good enough for manual approval or auto-approve
            from django.utils import timezone
            claim.status = PersonClaim.Status.VERIFIED
            claim.verified_at = timezone.now()
            claim.save()
            
            # Link membership
            membership.linked_person = person
            membership.save()
            
            messages.success(request, f"Identity verified! You are now linked to {person} in the family tree.")
            return redirect("families:family_tree_interactive", family_id=family.id)
        elif score >= 0.4:
            messages.warning(request, "The information didn't match well enough for automatic verification. An admin will review your claim.")
            return redirect("families:family_detail", family_id=family.id)
        else:
            # Too low - reject
            claim.status = PersonClaim.Status.REJECTED
            claim.notes = "Verification score too low"
            claim.save()
            messages.error(request, "The information you provided doesn't match our records. Please try again or contact an admin.")
            return redirect("families:find_my_match", family_id=family.id)
    
    # Show hints about what info is needed
    has_birth_date = person.birth_date is not None
    has_parents = father is not None or mother is not None
    
    return render(request, "families/verify_identity.html", {
        "family": family,
        "membership": membership,
        "claim": claim,
        "person": person,
        "has_birth_date": has_birth_date,
        "has_parents": has_parents,
        "person_birth_year": person.birth_date.year if person.birth_date else None,
    })


@login_required
def my_claims(request, family_id):
    """
    View all identity claims for the current user.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import PersonClaim
    
    claims = PersonClaim.objects.filter(
        user=request.user,
        family=family
    ).select_related('person').order_by('-created_at')
    
    return render(request, "families/my_claims.html", {
        "family": family,
        "membership": membership,
        "claims": claims,
    })


@login_required
def gedcom_import(request, family_id):
    """
    Import a GEDCOM file into the family tree.
    
    Uses enhanced import with tracking and duplicate detection.
    Creates a GedcomImport record and redirects to the import report.
    """
    from .forms import GedcomUploadForm
    from .gedcom import import_gedcom_with_tracking, GedcomParseError
    from .models import GedcomImport, PotentialDuplicate
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can import
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    # Recent imports for display
    recent_imports = GedcomImport.objects.filter(family=family).order_by('-created_at')[:5]
    
    # Count pending duplicates for this family
    pending_duplicate_count = PotentialDuplicate.objects.filter(
        gedcom_import__family=family,
        status='PENDING'
    ).count()
    
    if request.method == "POST":
        form = GedcomUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                # Read file content
                gedcom_file = form.cleaned_data['gedcom_file']
                content = gedcom_file.read().decode('utf-8', errors='ignore')
                file_name = gedcom_file.name
                file_size = gedcom_file.size
                
                # Check if a file with the same name was already imported
                existing_import = GedcomImport.objects.filter(
                    family=family,
                    file_name=file_name,
                    status__in=[GedcomImport.Status.COMPLETED, GedcomImport.Status.PROCESSING]
                ).first()
                
                if existing_import and not request.POST.get('confirm_duplicate'):
                    # Store file info in session for re-upload after confirmation
                    messages.warning(
                        request, 
                        f"A file named '{file_name}' was already imported on "
                        f"{existing_import.created_at.strftime('%b %d, %Y')} "
                        f"({existing_import.persons_created} people created). "
                        f"Check the box below to import anyway."
                    )
                    return render(request, "families/gedcom_import.html", {
                        "family": family,
                        "membership": membership,
                        "form": form,
                        "recent_imports": recent_imports,
                        "pending_duplicate_count": pending_duplicate_count,
                        "show_duplicate_warning": True,
                        "duplicate_file_name": file_name,
                        "existing_import": existing_import,
                    })
                
                # Import with tracking and duplicate detection
                gedcom_import_record = import_gedcom_with_tracking(
                    content, family, request.user, file_name, file_size
                )
                
                # Redirect to import report
                return redirect("families:gedcom_import_report", 
                               family_id=family.id, 
                               import_id=gedcom_import_record.id)
                
            except GedcomParseError as e:
                messages.error(request, f"Parse error: {str(e)}")
            except Exception as e:
                messages.error(request, f"Import failed: {str(e)}")
    else:
        form = GedcomUploadForm()
    
    return render(request, "families/gedcom_import.html", {
        "family": family,
        "membership": membership,
        "form": form,
        "recent_imports": recent_imports,
        "pending_duplicate_count": pending_duplicate_count,
    })


@login_required
def person_create(request, family_id):
    """
    Create a new person in the family tree.
    
    Also handles creating relationships (father, mother, spouse, children)
    if specified in the form.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot add people
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        form = PersonForm(request.POST, request.FILES, family=family)
        if form.is_valid():
            person = form.save(commit=False)
            person.family = family
            person.created_by = request.user
            person.save()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                person.photo.save(filename, content_file, save=True)
            
            # Create relationship records
            father = form.cleaned_data.get('father')
            mother = form.cleaned_data.get('mother')
            spouse = form.cleaned_data.get('spouse')
            children = form.cleaned_data.get('children')
            
            # Father relationship (father is parent, new person is child)
            if father:
                Relationship.objects.create(
                    family=family,
                    person1=father,
                    person2=person,
                    relationship_type=Relationship.Type.PARENT_CHILD
                )
            
            # Mother relationship (mother is parent, new person is child)
            if mother:
                Relationship.objects.create(
                    family=family,
                    person1=mother,
                    person2=person,
                    relationship_type=Relationship.Type.PARENT_CHILD
                )
            
            # Spouse relationship
            if spouse:
                Relationship.objects.create(
                    family=family,
                    person1=person,
                    person2=spouse,
                    relationship_type=Relationship.Type.SPOUSE
                )
            
            # Children relationships (new person is parent, children are children)
            if children:
                for child in children:
                    Relationship.objects.create(
                        family=family,
                        person1=person,
                        person2=child,
                        relationship_type=Relationship.Type.PARENT_CHILD
                    )

            recipients = [
                m.user for m in Membership.objects.filter(family=family).select_related("user")
                if m.user_id != request.user.id
            ]
            detail_bits = []
            if person.birth_date:
                detail_bits.append(f"b. {person.birth_date.strftime('%Y')}")
            if person.death_date:
                detail_bits.append(f"d. {person.death_date.strftime('%Y')}")
            subtitle = " · ".join(detail_bits)
            _notify_users(
                recipients=recipients,
                notification_type=Notification.NotificationType.PERSON,
                title=f"New family member added: {person.full_name}",
                message=subtitle or f"Added by { _display_name_for_user(request.user) }",
                link=f"/families/{family.id}/people/{person.id}/",
                family=family,
                request=request,
            )

            return redirect("families:person_detail", family_id=family.id, person_id=person.id)
    else:
        form = PersonForm(family=family)
    
    return render(request, "families/person_create.html", {
        "family": family,
        "membership": membership,
        "form": form,
    })


@login_required
def person_detail(request, family_id, person_id):
    """
    View details of a person in the family tree.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    person = get_object_or_404(Person, id=person_id, family=family)
    
    return render(request, "families/person_detail.html", {
        "family": family,
        "membership": membership,
        "person": person,
    })


@login_required
def person_edit(request, family_id, person_id):
    """
    Edit a person in the family tree.
    
    Also handles updating relationships (father, mother, spouse, children).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot edit
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    person = get_object_or_404(Person, id=person_id, family=family)
    
    if request.method == "POST":
        form = PersonForm(request.POST, request.FILES, instance=person, family=family)
        if form.is_valid():
            person = form.save()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                person.photo.save(filename, content_file, save=True)
            
            # Update relationships
            father = form.cleaned_data.get('father')
            mother = form.cleaned_data.get('mother')
            spouse = form.cleaned_data.get('spouse')
            other_parent = form.cleaned_data.get('other_parent')
            children = form.cleaned_data.get('children')
            
            # Update father relationship
            existing_father_rel = Relationship.objects.filter(
                person2=person,
                relationship_type=Relationship.Type.PARENT_CHILD,
                person1__gender=Person.Gender.MALE
            ).first()
            
            if father and not existing_father_rel:
                Relationship.objects.create(
                    family=family, person1=father, person2=person,
                    relationship_type=Relationship.Type.PARENT_CHILD
                )
            elif father and existing_father_rel and existing_father_rel.person1 != father:
                existing_father_rel.person1 = father
                existing_father_rel.save()
            elif not father and existing_father_rel:
                existing_father_rel.delete()
            
            # Update mother relationship
            existing_mother_rel = Relationship.objects.filter(
                person2=person,
                relationship_type=Relationship.Type.PARENT_CHILD,
                person1__gender=Person.Gender.FEMALE
            ).first()
            
            if mother and not existing_mother_rel:
                Relationship.objects.create(
                    family=family, person1=mother, person2=person,
                    relationship_type=Relationship.Type.PARENT_CHILD
                )
            elif mother and existing_mother_rel and existing_mother_rel.person1 != mother:
                existing_mother_rel.person1 = mother
                existing_mother_rel.save()
            elif not mother and existing_mother_rel:
                existing_mother_rel.delete()
            
            # Update spouse relationship
            existing_spouse_rel = Relationship.objects.filter(
                person1=person, relationship_type=Relationship.Type.SPOUSE
            ).first() or Relationship.objects.filter(
                person2=person, relationship_type=Relationship.Type.SPOUSE
            ).first()
            
            if spouse and not existing_spouse_rel:
                Relationship.objects.create(
                    family=family, person1=person, person2=spouse,
                    relationship_type=Relationship.Type.SPOUSE
                )
            elif spouse and existing_spouse_rel:
                # Update if different spouse
                current_spouse = existing_spouse_rel.person2 if existing_spouse_rel.person1 == person else existing_spouse_rel.person1
                if current_spouse != spouse:
                    existing_spouse_rel.delete()
                    Relationship.objects.create(
                        family=family, person1=person, person2=spouse,
                        relationship_type=Relationship.Type.SPOUSE
                    )
            elif not spouse and existing_spouse_rel:
                existing_spouse_rel.delete()
            
            # Update children relationships
            existing_children_rels = Relationship.objects.filter(
                person1=person, relationship_type=Relationship.Type.PARENT_CHILD
            )
            existing_children_ids = set(r.person2_id for r in existing_children_rels)
            new_children_ids = set(c.id for c in children) if children else set()
            
            # Remove children no longer selected
            for rel in existing_children_rels:
                if rel.person2_id not in new_children_ids:
                    rel.delete()
            
            # Add new children (and link to other parent if specified)
            for child in (children or []):
                if child.id not in existing_children_ids:
                    # Create relationship from this person to child
                    Relationship.objects.create(
                        family=family, person1=person, person2=child,
                        relationship_type=Relationship.Type.PARENT_CHILD
                    )
                
                # If other_parent is specified, create/update that relationship too
                if other_parent and other_parent.id != person.id:
                    # Check if other_parent already has a parent relationship with this child
                    existing_other_rel = Relationship.objects.filter(
                        person1=other_parent, person2=child,
                        relationship_type=Relationship.Type.PARENT_CHILD
                    ).first()
                    if not existing_other_rel:
                        Relationship.objects.create(
                            family=family, person1=other_parent, person2=child,
                            relationship_type=Relationship.Type.PARENT_CHILD
                        )
            
            return redirect("families:person_detail", family_id=family.id, person_id=person.id)
    else:
        form = PersonForm(instance=person, family=family)
    
    return render(request, "families/person_edit.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "form": form,
    })


@login_required
def person_delete(request, family_id, person_id):
    """
    Delete a person from the family tree (soft delete with audit trail).
    
    Only admins/owners can delete.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can delete
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    # Check if person exists but is already deleted
    person = Person.objects.filter(id=person_id, family=family).first()
    if not person:
        messages.error(request, "Person not found.")
        return redirect("families:family_tree", family_id=family.id)
    
    if person.is_deleted:
        messages.info(request, f"{person.full_name} is already in the trash bin.")
        return redirect("families:trash_bin", family_id=family.id)
    
    if request.method == "POST":
        # Store data for audit log before deletion
        previous_data = {
            'first_name': person.first_name,
            'last_name': person.last_name,
            'maiden_name': person.maiden_name,
            'gender': person.gender,
            'birth_date': str(person.birth_date) if person.birth_date else None,
            'death_date': str(person.death_date) if person.death_date else None,
            'birth_place': person.birth_place,
            'death_place': person.death_place,
            'bio': person.bio,
        }
        
        # Soft delete instead of hard delete
        person.soft_delete(request.user)
        
        # Create audit log
        AuditLog.log(
            family=family,
            user=request.user,
            action=AuditLog.Action.DELETE,
            obj=person,
            previous_data=previous_data,
            request=request
        )
        
        messages.success(request, f"{person.full_name} has been moved to trash. You can restore them from the trash bin.")
        return redirect("families:family_tree", family_id=family.id)
    
    return render(request, "families/person_delete.html", {
        "family": family,
        "membership": membership,
        "person": person,
    })


@login_required
def relationship_add(request, family_id, person_id):
    """
    Add a relationship for a person.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot add relationships
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    person = get_object_or_404(Person, id=person_id, family=family)
    
    if request.method == "POST":
        form = RelationshipForm(request.POST, family=family, exclude_person=person)
        if form.is_valid():
            rel = form.save(commit=False)
            rel.family = family
            rel.person1 = person
            rel.save()
            return redirect("families:person_detail", family_id=family.id, person_id=person.id)
    else:
        form = RelationshipForm(family=family, exclude_person=person)
    
    return render(request, "families/relationship_add.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "form": form,
    })


@login_required
def add_ancestor(request, family_id, person_id):
    """
    Add an ancestor (parent, grandparent, great-grandparent, etc.) to a person.
    
    This creates a new person and links them as a parent at the specified
    generation level. Generation levels:
        1 = Parent (direct parent)
        2 = Grandparent
        3 = Great-grandparent
        4 = 2x Great-grandparent
        ...up to 7 = 6x Great-grandparent
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot add ancestors
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    person = get_object_or_404(Person, id=person_id, family=family)
    
    # Get generation level from query param (default to 1 = parent)
    generation = int(request.GET.get('generation', 1))
    if generation < 1 or generation > 7:
        generation = 1
    
    # Determine which existing ancestor to attach to based on generation
    # We need to traverse up the tree to find where to attach
    target_person = person
    
    # For generation > 1, we need to find/create the chain
    # But for this initial implementation, user selects existing ancestor to add parent to
    attach_to_id = request.GET.get('attach_to', person_id)
    attach_to = get_object_or_404(Person, id=attach_to_id, family=family)
    
    # Determine generation label for display
    gen_labels = {
        1: "Parent",
        2: "Grandparent",
        3: "Great-grandparent",
        4: "2x Great-grandparent",
        5: "3x Great-grandparent",
        6: "4x Great-grandparent",
        7: "5x Great-grandparent",
        8: "6x Great-grandparent",
    }
    gen_label = gen_labels.get(generation, f"{generation-2}x Great-grandparent")
    
    if request.method == "POST":
        form = PersonForm(request.POST, request.FILES, family=family)
        if form.is_valid():
            ancestor = form.save(commit=False)
            ancestor.family = family
            ancestor.created_by = request.user
            ancestor.save()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                ancestor.photo.save(filename, content_file, save=True)
            
            # Create parent-child relationship: ancestor is PARENT of attach_to person
            Relationship.objects.create(
                family=family,
                person1=ancestor,  # Parent (the new ancestor)
                person2=attach_to,  # Child (the person we're attaching to)
                relationship_type=Relationship.Type.PARENT_CHILD
            )
            
            # If the form specified a spouse for this ancestor, create that too
            spouse = form.cleaned_data.get('spouse')
            if spouse:
                Relationship.objects.create(
                    family=family,
                    person1=ancestor,
                    person2=spouse,
                    relationship_type=Relationship.Type.SPOUSE
                )
            
            messages.success(request, f"Added {ancestor.full_name} as {gen_label.lower()} of {attach_to.full_name}.")
            
            # Redirect back to the original person's detail page
            return redirect("families:person_detail", family_id=family.id, person_id=person.id)
    else:
        form = PersonForm(family=family)
    
    # Get existing ancestors of the original person for the "attach to" dropdown
    def get_ancestors(p, depth=1, max_depth=7):
        """Recursively get all ancestors up to max_depth generations."""
        ancestors = []
        parent_rels = Relationship.objects.filter(
            person2=p,
            relationship_type=Relationship.Type.PARENT_CHILD,
            is_deleted=False
        ).select_related('person1')
        
        for rel in parent_rels:
            parent = rel.person1
            gen_label_inner = gen_labels.get(depth, f"{depth-2}x Great-grandparent")
            ancestors.append({
                'person': parent,
                'depth': depth,
                'label': gen_label_inner
            })
            if depth < max_depth:
                ancestors.extend(get_ancestors(parent, depth + 1, max_depth))
        
        return ancestors
    
    existing_ancestors = get_ancestors(person)
    
    return render(request, "families/add_ancestor.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "attach_to": attach_to,
        "generation": generation,
        "gen_label": gen_label,
        "form": form,
        "existing_ancestors": existing_ancestors,
    })


@login_required
def add_child(request, family_id, person_id):
    """
    Add a child to a person.
    
    This creates a new person and links them as a child of the current person.
    Useful for adding newly discovered children (e.g., via DNA testing).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot add children
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    person = get_object_or_404(Person, id=person_id, family=family)
    
    if request.method == "POST":
        form = PersonForm(request.POST, request.FILES, family=family)
        if form.is_valid():
            child = form.save(commit=False)
            child.family = family
            child.created_by = request.user
            child.save()
            
            # Handle cropped image if present
            content_file, filename = process_cropped_image(request)
            if content_file and filename:
                child.photo.save(filename, content_file, save=True)
            
            # Create parent-child relationship: current person is PARENT of the new child
            Relationship.objects.create(
                family=family,
                person1=person,  # Parent (the current person)
                person2=child,   # Child (the new person)
                relationship_type=Relationship.Type.PARENT_CHILD
            )
            
            # If the form specified an "other parent", create that relationship too
            other_parent = form.cleaned_data.get('other_parent')
            if other_parent and other_parent.id != person.id:
                Relationship.objects.create(
                    family=family,
                    person1=other_parent,  # Other parent
                    person2=child,         # Child
                    relationship_type=Relationship.Type.PARENT_CHILD
                )
            
            messages.success(request, f"Added {child.full_name} as child of {person.full_name}.")
            
            # Redirect back to the person's detail page
            return redirect("families:person_detail", family_id=family.id, person_id=person.id)
    else:
        form = PersonForm(family=family)
    
    return render(request, "families/add_child.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "form": form,
    })


@login_required
def relationship_delete(request, family_id, relationship_id):
    """
    Delete a relationship (soft delete).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot delete relationships
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    rel = get_object_or_404(Relationship, id=relationship_id, family=family, is_deleted=False)
    person_id = rel.person1_id
    
    if request.method == "POST":
        # Store data for audit log
        previous_data = {
            'person1': str(rel.person1),
            'person2': str(rel.person2),
            'relationship_type': rel.relationship_type,
            'start_date': str(rel.start_date) if rel.start_date else None,
            'end_date': str(rel.end_date) if rel.end_date else None,
        }
        
        # Soft delete
        rel.soft_delete(request.user)
        
        # Create audit log
        AuditLog.log(
            family=family,
            user=request.user,
            action=AuditLog.Action.DELETE,
            obj=rel,
            previous_data=previous_data,
            request=request
        )
        
        messages.success(request, "Relationship has been moved to trash.")
    
    return redirect("families:person_detail", family_id=family_id, person_id=person_id)


@login_required
def person_list(request, family_id):
    """
    List all persons in the family tree (excluding deleted).
    Includes online status for persons linked to user accounts.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    persons = Person.objects.filter(
        family=family, is_deleted=False
    ).select_related('linked_user__profile').order_by('last_name', 'first_name')
    
    # Build online status map for linked users
    online_status = {}
    for person in persons:
        if person.linked_user and hasattr(person.linked_user, 'profile'):
            online_status[person.id] = person.linked_user.profile.is_online()
    
    return render(request, "families/person_list.html", {
        "family": family,
        "membership": membership,
        "persons": persons,
        "online_status": online_status,
    })


# =============================================================================
# Phase 5: Photo Album Views
# =============================================================================

@login_required
def album_list(request, family_id):
    """
    List all photo albums for a family.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    albums = Album.objects.filter(family=family).select_related('event', 'primary_person', 'cover_photo').prefetch_related('photos')
    
    return render(request, "families/album_list.html", {
        "family": family,
        "membership": membership,
        "albums": albums,
    })


@login_required
def album_create(request, family_id):
    """
    Create a new photo album.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot create albums
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        form = AlbumForm(request.POST, family=family)
        if form.is_valid():
            album = form.save(commit=False)
            album.family = family
            album.created_by = request.user
            album.save()
            return redirect("families:album_detail", family_id=family.id, album_id=album.id)
    else:
        form = AlbumForm(family=family)
    
    return render(request, "families/album_create.html", {
        "family": family,
        "membership": membership,
        "form": form,
    })


@login_required
def album_detail(request, family_id, album_id):
    """
    View an album and its photos.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    album = get_object_or_404(Album, id=album_id, family=family)
    photos = album.photos.all().select_related('event', 'primary_person').prefetch_related('tagged_people')
    photo_items = photos.filter(media_type=Photo.MediaType.PHOTO)
    video_items = photos.filter(media_type=Photo.MediaType.VIDEO)
    document_items = photos.filter(media_type=Photo.MediaType.DOCUMENT)
    
    return render(request, "families/album_detail.html", {
        "family": family,
        "membership": membership,
        "album": album,
        "photos": photo_items,
        "videos": video_items,
        "documents": document_items,
    })


@login_required
def album_edit(request, family_id, album_id):
    """
    Edit album details.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot edit
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    album = get_object_or_404(Album, id=album_id, family=family)
    
    if request.method == "POST":
        form = AlbumForm(request.POST, instance=album, family=family)
        if form.is_valid():
            form.save()
            return redirect("families:album_detail", family_id=family.id, album_id=album.id)
    else:
        form = AlbumForm(instance=album, family=family)
    
    return render(request, "families/album_edit.html", {
        "family": family,
        "membership": membership,
        "album": album,
        "form": form,
    })


@login_required
def album_delete(request, family_id, album_id):
    """
    Delete an album and all its photos.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can delete albums
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    album = get_object_or_404(Album, id=album_id, family=family)
    
    if request.method == "POST":
        album.delete()
        return redirect("families:album_list", family_id=family.id)
    
    return render(request, "families/album_delete.html", {
        "family": family,
        "membership": membership,
        "album": album,
    })


@login_required
def photo_upload(request, family_id, album_id):
    """
    Upload photos to an album.
    
    Supports single and multiple file uploads.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot upload
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    album = get_object_or_404(Album, id=album_id, family=family)
    
    if request.method == "POST":
        # Handle quick multi-photo upload
        files = request.FILES.getlist('photos')
        if files:
            for f in files:
                if f.size > 10 * 1024 * 1024:
                    continue  # Skip oversized files
                Photo.objects.create(
                    album=album,
                    media_type=Photo.MediaType.PHOTO,
                    image=f,
                    uploaded_by=request.user,
                    event=album.event,
                    primary_person=album.primary_person,
                )
            return redirect("families:album_detail", family_id=family.id, album_id=album.id)

        # Single media upload with metadata
        form = PhotoUploadForm(request.POST, request.FILES, family=family)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.album = album
            photo.uploaded_by = request.user
            if not photo.event:
                photo.event = album.event
            if not photo.primary_person:
                photo.primary_person = album.primary_person
            photo.save()
            form.save_m2m()  # Save tagged_people
            return redirect("families:album_detail", family_id=family.id, album_id=album.id)
    else:
        form = PhotoUploadForm(family=family, initial={
            "event": album.event_id,
            "primary_person": album.primary_person_id,
        })
    
    return render(request, "families/photo_upload.html", {
        "family": family,
        "membership": membership,
        "album": album,
        "form": form,
    })


@login_required
def photo_detail(request, family_id, album_id, photo_id):
    """
    View a single photo with full details.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    album = get_object_or_404(Album, id=album_id, family=family)
    photo = get_object_or_404(Photo, id=photo_id, album=album)
    
    # Get previous and next photos for navigation
    photos_list = list(album.photos.values_list('id', flat=True))
    current_index = photos_list.index(photo.id) if photo.id in photos_list else 0
    prev_photo = photos_list[current_index - 1] if current_index > 0 else None
    next_photo = photos_list[current_index + 1] if current_index < len(photos_list) - 1 else None
    
    return render(request, "families/photo_detail.html", {
        "family": family,
        "membership": membership,
        "album": album,
        "photo": photo,
        "prev_photo_id": prev_photo,
        "next_photo_id": next_photo,
    })


@login_required
def photo_tag_suggestions(request, family_id, album_id, photo_id):
    """
    Provide simple tag suggestions based on people already tagged in the same album.
    Acts as a lightweight face-rec placeholder by using tag frequency proximity.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"suggestions": []})

    album = get_object_or_404(Album, id=album_id, family=family)
    photo = get_object_or_404(Photo, id=photo_id, album=album)

    # People tagged in this album's photos, ordered by frequency
    from django.db.models import Count
    counts = (
        Person.objects.filter(
            tagged_photos__album=album,
            is_deleted=False,
            linked_user__isnull=False,
            death_date__isnull=True,
        )
        .exclude(tagged_photos=photo)
        .annotate(freq=Count("tagged_photos"))
        .order_by("-freq", "last_name", "first_name")[:5]
    )
    suggestions = [
        {
            "id": p.id,
            "name": p.full_name,
            "freq": p.freq,
            "confidence": min(0.95, 0.4 + 0.1 * p.freq),  # heuristic confidence
            "reason": "Similar faces in this album (placeholder)",
        }
        for p in counts
        if p.id not in photo.tagged_people.values_list("id", flat=True)
    ]
    return JsonResponse({"suggestions": suggestions})


@login_required
def photo_edit(request, family_id, album_id, photo_id):
    """
    Edit photo details (caption, date, location, tags).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot edit
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    album = get_object_or_404(Album, id=album_id, family=family)
    photo = get_object_or_404(Photo, id=photo_id, album=album)
    
    if request.method == "POST":
        form = PhotoUploadForm(request.POST, request.FILES, instance=photo, family=family)
        if form.is_valid():
            form.save()
            # Handle optional manual tag by name
            manual_tag_name = request.POST.get("manual_tag_name", "").strip()
            if manual_tag_name:
                # Try to find matching people in this family (case-insensitive contains)
                matches = Person.objects.filter(
                    family=family,
                    is_deleted=False,
                    linked_user__isnull=False,
                    death_date__isnull=True,
                    first_name__icontains=manual_tag_name.split()[0]
                )
                if matches:
                    photo.tagged_people.add(*list(matches[:5]))
                else:
                    messages.warning(request, f"No matching family member found for '{manual_tag_name}'.")
            redirect_to = request.POST.get("redirect_to")
            if redirect_to == "detail":
                return redirect("families:photo_detail", family_id=family.id, album_id=album.id, photo_id=photo.id)
            return redirect("families:photo_detail", family_id=family.id, album_id=album.id, photo_id=photo.id)
    else:
        form = PhotoUploadForm(instance=photo, family=family)
    
    return render(request, "families/photo_edit.html", {
        "family": family,
        "membership": membership,
        "album": album,
        "photo": photo,
        "form": form,
    })


@login_required
def photo_delete(request, family_id, album_id, photo_id):
    """
    Delete a photo.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner or uploader can delete
    album = get_object_or_404(Album, id=album_id, family=family)
    photo = get_object_or_404(Photo, id=photo_id, album=album)
    
    can_delete = (
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN] or
        photo.uploaded_by == request.user
    )
    
    if not can_delete:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        photo.delete()
        return redirect("families:album_detail", family_id=family.id, album_id=album.id)
    
    return render(request, "families/photo_delete.html", {
        "family": family,
        "membership": membership,
        "album": album,
        "photo": photo,
    })


@login_required
def photo_set_cover(request, family_id, album_id, photo_id):
    """
    Set a photo as the album cover.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return redirect("families:album_detail", family_id=family_id, album_id=album_id)
    
    # Viewers cannot set cover
    if membership.role == Membership.Role.VIEWER:
        return redirect("families:album_detail", family_id=family_id, album_id=album_id)
    
    album = get_object_or_404(Album, id=album_id, family=family)
    photo = get_object_or_404(Photo, id=photo_id, album=album)

    if photo.media_type != Photo.MediaType.PHOTO:
        messages.error(request, "Only photos can be used as album covers.")
        return redirect("families:album_detail", family_id=family_id, album_id=album_id)
    
    album.cover_photo = photo
    album.save()
    
    return redirect("families:album_detail", family_id=family_id, album_id=album_id)


# =============================================================================
# Living Museum - Stories, Memories & Tributes Views
# =============================================================================

@login_required
def museum_home(request, family_id):
    """
    Living Museum home page for a family.
    
    Displays featured memories, recent stories, and browse options.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MemoryStory
    
    story_type = request.GET.get("story_type", "").strip()
    person_id = request.GET.get("person", "").strip()
    search_query = request.GET.get("q", "").strip()

    # Get featured memories
    featured_memories = MemoryStory.objects.filter(
        person__family=family,
        is_featured=True
    ).select_related('person', 'author').prefetch_related('media').order_by('-created_at')[:6]

    memories = MemoryStory.objects.filter(
        person__family=family
    ).select_related('person', 'author').prefetch_related('media', 'reactions', 'comments').order_by('-is_featured', '-created_at')

    if story_type:
        memories = memories.filter(story_type=story_type)
    if person_id.isdigit():
        memories = memories.filter(person_id=person_id)
    if search_query:
        memories = memories.filter(
            Q(title__icontains=search_query) |
            Q(content__icontains=search_query) |
            Q(person__first_name__icontains=search_query) |
            Q(person__last_name__icontains=search_query)
        )

    paginator = Paginator(memories, 12)
    memories_page = paginator.get_page(request.GET.get("page"))

    # Get people with memories for discovery and filters
    people = Person.objects.filter(
        family=family,
        is_deleted=False,
        memories__isnull=False
    ).distinct().order_by('last_name', 'first_name')

    # Get persons with memories for highlights
    persons_with_memories = Person.objects.filter(
        family=family,
        is_deleted=False,
        memories__isnull=False
    ).distinct().annotate(
        memory_count=Count('memories')
    ).order_by('-memory_count')[:10]

    # Memory type counts
    memory_type_counts = MemoryStory.objects.filter(
        person__family=family
    ).values('story_type').annotate(count=Count('id'))

    return render(request, "families/museum_home.html", {
        "family": family,
        "membership": membership,
        "featured_memories": featured_memories,
        "memories": memories_page,
        "people": people,
        "story_types": MemoryStory.StoryType.choices,
        "current_story_type": story_type,
        "current_person_id": person_id,
        "search_query": search_query,
        "persons_with_memories": persons_with_memories,
        "memory_type_counts": {m['story_type']: m['count'] for m in memory_type_counts},
        "total_memories": memories.count(),
    })


@login_required
def museum_person(request, family_id, person_id):
    """
    View all memories/stories for a specific person.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MemoryStory
    
    person = get_object_or_404(Person, id=person_id, family=family, is_deleted=False)
    
    # Get all memories for this person
    memories = MemoryStory.objects.filter(
        person=person
    ).select_related('author').prefetch_related('media', 'reactions').order_by('-is_featured', '-created_at')
    
    # Filter by type if requested
    story_type = request.GET.get('type')
    if story_type:
        memories = memories.filter(story_type=story_type)

    story_type_counts = []
    for type_code, type_name in MemoryStory.StoryType.choices:
        story_type_counts.append((type_code, type_name, person.memories.filter(story_type=type_code).count()))

    return render(request, "families/museum_person.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "memories": memories,
        "story_types": MemoryStory.StoryType.choices,
        "current_type": story_type,
        "story_type_counts": story_type_counts,
        "total_memories": person.memories.count(),
        "total_media": MemoryMedia.objects.filter(memory__person=person).count(),
    })


@login_required
def memory_detail(request, family_id, memory_id):
    """
    View a single memory story with all media and comments.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MemoryStory, MemoryComment, MemoryReaction
    
    memory = get_object_or_404(
        MemoryStory.objects.select_related('person', 'author').prefetch_related('media', 'comments__author', 'reactions'),
        id=memory_id,
        person__family=family
    )
    
    # Increment view count
    memory.view_count += 1
    memory.save(update_fields=['view_count'])
    
    # Check if user has reacted
    user_reaction = MemoryReaction.objects.filter(memory=memory, user=request.user).first()
    
    # Get reaction counts
    reaction_counts = memory.reactions.values('reaction_type').annotate(count=models.Count('id'))
    
    return render(request, "families/memory_detail.html", {
        "family": family,
        "membership": membership,
        "memory": memory,
        "user_reaction": user_reaction,
        "reaction_counts": {r['reaction_type']: r['count'] for r in reaction_counts},
        "reaction_types": MemoryReaction.ReactionType.choices,
    })


@login_required
def memory_create(request, family_id, person_id=None, *args, **kwargs):
    """
    Create a new memory/story for a person.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot create memories
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    from .models import MemoryStory, MemoryMedia
    
    # Get selected person if provided
    selected_person = None
    if person_id:
        selected_person = get_object_or_404(Person, id=person_id, family=family, is_deleted=False)
    
    # Get all people for dropdown
    people = Person.objects.filter(family=family, is_deleted=False).order_by('first_name', 'last_name')
    
    if request.method == "POST":
        # Get person from form if not pre-selected
        if not selected_person:
            person_form_id = request.POST.get('person')
            if person_form_id:
                selected_person = get_object_or_404(Person, id=person_form_id, family=family, is_deleted=False)
        
        if not selected_person:
            messages.error(request, "Please select a person for this memory.")
            return render(request, "families/memory_create.html", {
                "family": family,
                "membership": membership,
                "people": people,
                "selected_person": None,
                "story_types": MemoryStory.StoryType.choices,
            })
        
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        story_type = request.POST.get('story_type', MemoryStory.StoryType.MEMORY)
        date_of_memory = request.POST.get('date_of_memory') or None
        location = request.POST.get('location', '').strip()
        is_featured = request.POST.get('is_featured') == 'on'
        is_public = request.POST.get('is_public') == 'on'
        
        if title and content:
            memory = MemoryStory.objects.create(
                person=selected_person,
                title=title,
                content=content,
                story_type=story_type,
                author=request.user,
                date_of_memory=date_of_memory if date_of_memory else None,
                location=location,
                is_featured=is_featured,
                is_public=is_public,
            )
            
            # Handle file uploads
            files = request.FILES.getlist('media')
            for i, f in enumerate(files):
                # Determine media type from file
                content_type = f.content_type
                if content_type.startswith('image/'):
                    media_type = MemoryMedia.MediaType.PHOTO
                elif content_type.startswith('video/'):
                    media_type = MemoryMedia.MediaType.VIDEO
                elif content_type.startswith('audio/'):
                    media_type = MemoryMedia.MediaType.AUDIO
                else:
                    media_type = MemoryMedia.MediaType.DOCUMENT
                
                MemoryMedia.objects.create(
                    memory=memory,
                    media_type=media_type,
                    file=f,
                    order=i,
                    uploaded_by=request.user,
                )
            
            messages.success(request, f"Memory '{title}' has been added to {selected_person.full_name}'s story.")
            return redirect("families:memory_detail", family_id=family.id, memory_id=memory.id)
        else:
            messages.error(request, "Please provide a title and content for the memory.")
    
    return render(request, "families/memory_create.html", {
        "family": family,
        "membership": membership,
        "selected_person": selected_person,
        "people": people,
        "story_types": MemoryStory.StoryType.choices,
        "is_admin": membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN],
    })


@login_required
def life_story(request, family_id, person_id):
    """View and edit a person's life story with ordered sections."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    person = get_object_or_404(Person, id=person_id, family=family, is_deleted=False)
    life_story = person.life_stories.order_by("-created_at").first()
    if not life_story:
        life_story = LifeStory.objects.create(person=person, created_by=request.user, title=f"{person.full_name}'s Life Story")

    sections = life_story.sections.all()

    if request.method == "POST":
        form = LifeStorySectionForm(request.POST, request.FILES)
        if form.is_valid():
            section = form.save(commit=False)
            section.life_story = life_story
            section.save()
            return redirect("families:life_story", family_id=family.id, person_id=person.id)
    else:
        form = LifeStorySectionForm()

    return render(request, "families/life_story.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "life_story": life_story,
        "sections": sections,
        "form": form,
    })


@login_required
def time_capsule_list(request, family_id):
    """List time capsules for a family."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    capsules = TimeCapsule.objects.filter(family=family).order_by("open_at")
    return render(request, "families/time_capsule_list.html", {
        "family": family,
        "membership": membership,
        "capsules": capsules,
    })


@login_required
def time_capsule_detail(request, family_id, capsule_id):
    """View a time capsule; unlock if due."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    capsule = get_object_or_404(TimeCapsule, id=capsule_id, family=family)
    if capsule.is_unlocked and not capsule.is_opened:
        capsule.is_opened = True
        capsule.save(update_fields=["is_opened"])

    return render(request, "families/time_capsule_detail.html", {
        "family": family,
        "membership": membership,
        "capsule": capsule,
    })


@login_required
def time_capsule_create(request, family_id):
    """Create a new time capsule entry."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    if request.method == "POST":
        form = TimeCapsuleForm(request.POST, request.FILES)
        if form.is_valid():
            capsule = form.save(commit=False)
            capsule.family = family
            capsule.created_by = request.user
            capsule.save()
            return redirect("families:time_capsule_detail", family_id=family.id, capsule_id=capsule.id)
    else:
        form = TimeCapsuleForm()

    return render(request, "families/time_capsule_create.html", {
        "family": family,
        "membership": membership,
        "form": form,
    })


@login_required
def person_chatbot(request, family_id, person_id):
    """
    Lightweight person-aware summary/QA endpoint (no external AI).
    Returns a synthesized narrative and simple retrieval-based answer.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    person = get_object_or_404(Person, id=person_id, family=family, is_deleted=False)

    memories = (
        MemoryStory.objects.filter(person=person)
        .order_by("-is_featured", "-created_at")
        .prefetch_related("media")
    )[:10]
    story_sections = (
        person.life_stories.first().sections.all() if person.life_stories.exists() else []
    )
    events = (
        Event.objects.filter(family=family, title__icontains=person.first_name)
        .order_by("-start_datetime")[:5]
    )
    question = request.GET.get("q", "").strip()

    def summarize():
        parts = [f"{person.full_name} — quick story snapshot:"]
        if person.birth_date:
            parts.append(f"- Born: {person.birth_date}")
        if person.death_date:
            parts.append(f"- Passed: {person.death_date}")
        if memories:
            parts.append(f"- Top memories ({len(memories)}): " + "; ".join(m.title for m in memories[:3]))
        if story_sections:
            parts.append(f"- Life story sections: " + "; ".join(s.heading for s in story_sections[:4]))
        if events:
            parts.append(f"- Related events: " + "; ".join(e.title for e in events))
        return "\n".join(parts)

    response_text = summarize()

    answer = ""
    if question:
        corpus = []
        corpus.extend([f"{m.title}: {m.content}" for m in memories])
        corpus.extend([f"{s.heading}: {s.content}" for s in story_sections])
        corpus.extend([f"Event {e.title}: {e.description}" for e in events if e.description])
        from difflib import get_close_matches
        best = get_close_matches(question.lower(), [c.lower() for c in corpus], n=1, cutoff=0.1)
        if best:
            idx = [c.lower() for c in corpus].index(best[0])
            answer = corpus[idx]
        else:
            answer = "I couldn't find an exact answer, but here's the latest summary:\n" + response_text

    return render(request, "families/person_chatbot.html", {
        "family": family,
        "membership": membership,
        "person": person,
        "response_text": response_text,
        "question": question,
        "answer": answer,
    })


@login_required
def memory_edit(request, family_id, memory_id):
    """
    Edit an existing memory/story.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MemoryStory, MemoryMedia
    
    memory = get_object_or_404(MemoryStory, id=memory_id, person__family=family)
    
    # Only author or admin can edit
    can_edit = (
        memory.author == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    if not can_edit:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        memory.title = request.POST.get('title', memory.title).strip()
        memory.content = request.POST.get('content', memory.content).strip()
        memory.story_type = request.POST.get('story_type', memory.story_type)
        date_of_memory = request.POST.get('date_of_memory')
        memory.date_of_memory = date_of_memory if date_of_memory else None
        memory.location = request.POST.get('location', '').strip()
        memory.is_featured = request.POST.get('is_featured') == 'on'
        memory.is_public = request.POST.get('is_public') == 'on'
        memory.save()
        
        # Handle new file uploads
        files = request.FILES.getlist('media')
        existing_count = memory.media.count()
        for i, f in enumerate(files):
            content_type = f.content_type
            if content_type.startswith('image/'):
                media_type = MemoryMedia.MediaType.PHOTO
            elif content_type.startswith('video/'):
                media_type = MemoryMedia.MediaType.VIDEO
            elif content_type.startswith('audio/'):
                media_type = MemoryMedia.MediaType.AUDIO
            else:
                media_type = MemoryMedia.MediaType.DOCUMENT
            
            MemoryMedia.objects.create(
                memory=memory,
                media_type=media_type,
                file=f,
                order=existing_count + i,
                uploaded_by=request.user,
            )
        
        messages.success(request, "Memory has been updated.")
        return redirect("families:memory_detail", family_id=family.id, memory_id=memory.id)
    
    return render(request, "families/memory_edit.html", {
        "family": family,
        "membership": membership,
        "memory": memory,
        "story_types": MemoryStory.StoryType.choices,
    })


@login_required
def memory_delete(request, family_id, memory_id):
    """
    Delete a memory/story.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MemoryStory
    
    memory = get_object_or_404(MemoryStory, id=memory_id, person__family=family)
    person = memory.person
    
    # Only author or admin can delete
    can_delete = (
        memory.author == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    if not can_delete:
        return render(request, "families/no_access.html", {"family": family})
    
    if request.method == "POST":
        memory.delete()
        messages.success(request, "Memory has been deleted.")
        return redirect("families:museum_person", family_id=family.id, person_id=person.id)
    
    return render(request, "families/memory_delete.html", {
        "family": family,
        "membership": membership,
        "memory": memory,
    })


@login_required
def memory_react(request, family_id, memory_id):
    """
    Add or change reaction to a memory.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    from .models import MemoryStory, MemoryReaction
    
    memory = get_object_or_404(MemoryStory, id=memory_id, person__family=family)
    
    if request.method == "POST":
        reaction_type = request.POST.get('reaction_type')
        
        if reaction_type == 'remove':
            # Remove existing reaction
            MemoryReaction.objects.filter(memory=memory, user=request.user).delete()
        elif reaction_type in dict(MemoryReaction.ReactionType.choices):
            # Add or update reaction
            reaction, created = MemoryReaction.objects.update_or_create(
                memory=memory,
                user=request.user,
                defaults={'reaction_type': reaction_type}
            )
        
        # Return via AJAX or redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            reaction_counts = memory.reactions.values('reaction_type').annotate(count=models.Count('id'))
            return JsonResponse({
                "success": True,
                "reaction_counts": {r['reaction_type']: r['count'] for r in reaction_counts},
                "total": memory.reactions.count(),
            })
        
        return redirect("families:memory_detail", family_id=family.id, memory_id=memory.id)
    
    return JsonResponse({"error": "POST required"}, status=405)


@login_required
def memory_comment(request, family_id, memory_id):
    """
    Add a comment to a memory.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot comment
    if membership.role == Membership.Role.VIEWER:
        return redirect("families:memory_detail", family_id=family.id, memory_id=memory_id)
    
    from .models import MemoryStory, MemoryComment
    
    memory = get_object_or_404(MemoryStory, id=memory_id, person__family=family)
    
    if request.method == "POST":
        content = request.POST.get('content', '').strip()
        if content:
            MemoryComment.objects.create(
                memory=memory,
                author=request.user,
                content=content,
            )
            messages.success(request, "Your comment has been added.")
    
    return redirect("families:memory_detail", family_id=family.id, memory_id=memory.id)


@login_required
def memory_media_delete(request, family_id, memory_id, media_id):
    """
    Delete media from a memory.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    from .models import MemoryStory, MemoryMedia
    
    memory = get_object_or_404(MemoryStory, id=memory_id, person__family=family)
    media = get_object_or_404(MemoryMedia, id=media_id, memory=memory)
    
    # Only author or admin can delete media
    can_delete = (
        memory.author == request.user or
        media.uploaded_by == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    if not can_delete:
        return JsonResponse({"error": "Permission denied"}, status=403)
    
    if request.method == "POST":
        media.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"success": True})
        
        messages.success(request, "Media has been removed.")
        return redirect("families:memory_edit", family_id=family.id, memory_id=memory.id)
    
    return JsonResponse({"error": "POST required"}, status=405)


# =============================================================================
# Museum Sharing Views
# =============================================================================

@login_required
def museum_share_create(request, family_id, share_type=None, object_id=None):
    """
    Create a share link for the museum or specific content.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MuseumShare, MemoryStory
    
    normalized_share_type = (share_type or "").upper()
    memory = None
    person = None
    if object_id and normalized_share_type == MuseumShare.ShareType.MEMORY:
        memory = get_object_or_404(MemoryStory, id=object_id, person__family=family)
    elif object_id and normalized_share_type == MuseumShare.ShareType.PERSON:
        person = get_object_or_404(Person, id=object_id, family=family, is_deleted=False)

    if request.method == "POST":
        raw_share_type = request.POST.get('share_type', share_type or MuseumShare.ShareType.MUSEUM)
        normalized_share_type = (raw_share_type or MuseumShare.ShareType.MUSEUM).upper()
        memory_id = request.POST.get('memory_id')
        person_id = request.POST.get('person_id')
        shared_with_email = request.POST.get('shared_with_email', request.POST.get('email', '')).strip()
        share_method = request.POST.get('share_method', 'link')
        is_public_link = share_method == 'link' or request.POST.get('is_public') == 'on'
        message = request.POST.get('message', '').strip()
        expires_days = request.POST.get('expires_in', request.POST.get('expires_days'))
        
        # Calculate expiration
        expires_at = None
        if expires_days and expires_days.isdigit():
            from django.utils import timezone
            from datetime import timedelta
            expires_at = timezone.now() + timedelta(days=int(expires_days))
        
        share = MuseumShare(
            share_type=normalized_share_type,
            shared_by=request.user,
            shared_with_email=shared_with_email,
            is_public_link=is_public_link,
            message=message,
            expires_at=expires_at,
        )

        # Set what is being shared
        if normalized_share_type == MuseumShare.ShareType.MEMORY and memory_id:
            memory = get_object_or_404(MemoryStory, id=memory_id, person__family=family)
            share.memory = memory
        elif normalized_share_type == MuseumShare.ShareType.PERSON and person_id:
            person = get_object_or_404(Person, id=person_id, family=family, is_deleted=False)
            share.person = person
        else:
            share.share_type = MuseumShare.ShareType.MUSEUM
            share.family = family
        
        share.save()
        
        # If shared with email, try to find user
        if shared_with_email:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                recipient = User.objects.get(email__iexact=shared_with_email)
                share.shared_with_user = recipient
                share.save()
                
                # Create notification for recipient
                create_notification(
                    recipient=recipient,
                    notification_type=Notification.NotificationType.SYSTEM,
                    title=f"Museum shared with you",
                    message=f"{request.user.email} shared memories with you",
                    link=share.get_share_url(),
                    family=family
                )
            except User.DoesNotExist:
                pass
        
        messages.success(request, "Share link created successfully!")
        
        # Return share URL for copying
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                "success": True,
                "share_url": request.build_absolute_uri(share.get_share_url()),
                "share_token": share.share_token,
            })
        
        return redirect("families:museum_share_list", family_id=family.id)
    
    # Get persons and memories for the form
    persons = Person.objects.filter(family=family, is_deleted=False).order_by('last_name', 'first_name')
    memories = MemoryStory.objects.filter(person__family=family).select_related('person')[:50]

    return render(request, "families/museum_share_create.html", {
        "family": family,
        "membership": membership,
        "share_type": normalized_share_type.lower() if normalized_share_type else "",
        "person": person,
        "memory": memory,
        "people": persons,
        "persons": persons,
        "memories": memories,
        "share_types": MuseumShare.ShareType.choices,
    })


@login_required
def museum_share_list(request, family_id):
    """
    List all shares created by the user for this family's museum.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    from .models import MuseumShare
    
    # Get shares created by this user or for this family (if admin)
    if membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        shares = MuseumShare.objects.filter(
            models.Q(family=family) | 
            models.Q(person__family=family) | 
            models.Q(memory__person__family=family)
        ).select_related('shared_by', 'shared_with_user', 'memory', 'person')
    else:
        shares = MuseumShare.objects.filter(
            shared_by=request.user
        ).filter(
            models.Q(family=family) | 
            models.Q(person__family=family) | 
            models.Q(memory__person__family=family)
        ).select_related('shared_with_user', 'memory', 'person')

    now = timezone.now()
    return render(request, "families/museum_share_list.html", {
        "family": family,
        "membership": membership,
        "shares": shares,
        "active_shares": sum(1 for share in shares if share.is_valid()),
        "expired_shares": sum(1 for share in shares if not share.is_valid()),
        "total_views": sum(share.view_count for share in shares),
        "now": now,
    })


@login_required
def museum_share_delete(request, family_id, share_id):
    """
    Delete/revoke a share.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    from .models import MuseumShare
    
    share = get_object_or_404(
        MuseumShare,
        Q(id=share_id),
        Q(family=family) | Q(person__family=family) | Q(memory__person__family=family),
    )
    
    # Check permission
    can_delete = (
        share.shared_by == request.user or
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]
    )
    if not can_delete:
        return JsonResponse({"error": "Permission denied"}, status=403)
    
    if request.method == "POST":
        share.delete()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"success": True})
        
        messages.success(request, "Share has been revoked.")
        return redirect("families:museum_share_list", family_id=family.id)

    return render(request, "families/museum_share_delete.html", {
        "family": family,
        "membership": membership,
        "share": share,
    })


def museum_shared_view(request, share_token):
    """
    Public view for shared museum content.
    
    No login required if share is a public link.
    """
    from .models import MuseumShare, MemoryStory
    
    share = get_object_or_404(MuseumShare, share_token=share_token)
    
    # Check if share is valid
    if not share.is_valid():
        return render(request, "families/museum_share_expired.html", {
            "share": share,
        })
    
    # Check access
    user = request.user if request.user.is_authenticated else None
    if not share.can_access(user):
        if not user:
            # Redirect to login
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return render(request, "families/museum_share_denied.html", {
            "share": share,
        })
    
    # Record view
    share.record_view()
    
    # Get content based on share type
    context = {
        "share": share,
        "is_shared_view": True,
    }
    
    if share.share_type == MuseumShare.ShareType.MEMORY and share.memory:
        context["memory"] = share.memory
        context["memory"].view_count += 1
        context["memory"].save(update_fields=['view_count'])
        return render(request, "families/museum_shared_view.html", context)
    
    elif share.share_type == MuseumShare.ShareType.PERSON and share.person:
        context["person"] = share.person
        context["memories"] = MemoryStory.objects.filter(
            person=share.person,
            is_public=True  # Only show public memories
        ).select_related('author').prefetch_related('media')
        return render(request, "families/museum_shared_view.html", context)
    
    elif share.share_type == MuseumShare.ShareType.MUSEUM and share.family:
        context["family"] = share.family
        context["memories"] = MemoryStory.objects.filter(
            person__family=share.family,
            is_public=True
        ).select_related('person', 'author').prefetch_related('media')[:50]
        context["persons_with_memories"] = Person.objects.filter(
            family=share.family,
            is_deleted=False,
            memories__is_public=True
        ).distinct()
        return render(request, "families/museum_shared_view.html", context)

    return render(request, "families/museum_share_error.html", context)


@login_required
def museum_my_shares(request):
    """
    View all shares the current user has received or created.
    """
    from .models import MuseumShare
    
    # Shares received
    received_shares = MuseumShare.objects.filter(
        models.Q(shared_with_user=request.user) |
        models.Q(shared_with_email__iexact=request.user.email)
    ).filter(is_active=True).select_related('shared_by', 'memory', 'person', 'family')
    
    # Shares created
    created_shares = MuseumShare.objects.filter(
        shared_by=request.user
    ).select_related('shared_with_user', 'memory', 'person', 'family')[:50]
    
    return render(request, "families/museum_my_shares.html", {
        "received_shares": received_shares,
        "created_shares": created_shares,
        "now": timezone.now(),
    })


# =============================================================================
# Phase 6: Notifications & Messaging Views
# =============================================================================

@login_required
def notification_list(request):
    """
    Display all notifications for the current user.
    
    Shows a paginated list of notifications with read/unread status.
    """
    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related('family')[:100]
    
    unread_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    
    return render(request, "families/notification_list.html", {
        "notifications": notifications,
        "unread_count": unread_count,
    })


@login_required
def notification_mark_read(request, notification_id):
    """
    Mark a single notification as read.
    """
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        recipient=request.user
    )
    notification.is_read = True
    notification.save()
    
    # If there's a link, redirect to it
    if notification.link:
        return redirect(notification.link)
    
    return redirect("families:notification_list")


@login_required
def notification_mark_all_read(request):
    """
    Mark all notifications as read for the current user.
    """
    if request.method == "POST":
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)
    
    return redirect("families:notification_list")


@login_required
def notification_dropdown(request):
    """
    JSON endpoint for notification bell dropdown.
    Returns recent unread notifications for AJAX loading.
    """
    notifications = Notification.objects.filter(
        recipient=request.user
    ).select_related('family').order_by('-created_at')[:10]
    
    unread_count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    
    data = {
        "unread_count": unread_count,
        "notifications": [
            {
                "id": n.id,
                "type": n.notification_type,
                "title": n.title,
                "message": n.message[:100] if n.message else "",
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
                "family_name": n.family.name if n.family else None,
            }
            for n in notifications
        ]
    }
    
    return JsonResponse(data)


@login_required
def messaging_hub(request, family_id):
    """
    Unified messaging hub for family, direct, branch, and event conversations.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    _get_or_create_family_conversation(family, request.user)

    participations = ChatConversationParticipant.objects.filter(
        user=request.user,
        conversation__family=family,
    ).select_related(
        "conversation",
        "conversation__branch_root",
        "conversation__event",
    ).prefetch_related(
        "conversation__participants__user",
        "conversation__participants__user__profile",
        "conversation__messages",
    ).order_by("-conversation__updated_at")

    conversations = []
    for participation in participations:
        conversation = participation.conversation
        latest_message = conversation.messages.filter(is_deleted=False).select_related("author").order_by("-created_at").first()
        unread_count = conversation.messages.filter(is_deleted=False).exclude(
            author=request.user
        ).exclude(
            read_receipts__user=request.user
        ).count()
        conversations.append({
            "conversation": conversation,
            "title": _conversation_title(conversation, request.user),
            "latest_message": latest_message,
            "unread_count": unread_count,
        })

    members = Membership.objects.filter(
        family=family
    ).exclude(user=request.user).select_related("user", "user__profile").order_by("user__email")
    branch_people = Person.objects.filter(
        family=family,
        is_deleted=False,
        linked_user__isnull=False,
        death_date__isnull=True,
    ).order_by("last_name", "first_name")[:20]
    events = Event.objects.filter(family=family).order_by("-start_datetime")[:10]

    return render(request, "families/messaging_hub.html", {
        "family": family,
        "membership": membership,
        "conversations": conversations,
        "members": members,
        "branch_people": branch_people,
        "events": events,
    })


@login_required
def direct_conversation_start(request, family_id, user_id):
    """Create or open a direct conversation with another family member."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    if user_id == request.user.id:
        return redirect("families:messaging_hub", family_id=family.id)

    other_membership = get_object_or_404(Membership.objects.select_related("user"), family=family, user_id=user_id)
    conversation = _get_or_create_direct_conversation(family, request.user, other_membership.user)
    return redirect("families:conversation_room", family_id=family.id, conversation_id=conversation.id)


@login_required
def branch_conversation_start(request, family_id, person_id):
    """Create or open a branch conversation."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    person = get_object_or_404(Person, id=person_id, family=family, is_deleted=False)
    conversation = _get_or_create_branch_conversation(family, request.user, person)
    return redirect("families:conversation_room", family_id=family.id, conversation_id=conversation.id)


@login_required
def event_conversation_start(request, family_id, event_id):
    """Create or open an event conversation."""
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    event = get_object_or_404(Event, id=event_id, family=family)
    conversation = _get_or_create_event_conversation(family, request.user, event)
    return redirect("families:conversation_room", family_id=family.id, conversation_id=conversation.id)


@login_required
def conversation_room(request, family_id, conversation_id):
    """
    Realtime room for a unified conversation.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    conversation = get_object_or_404(
        ChatConversation.objects.select_related("family", "branch_root", "event"),
        id=conversation_id,
        family=family,
    )
    if conversation.conversation_type != ChatConversation.ConversationType.DIRECT:
        _ensure_shared_conversation_participants(conversation)
    participant = ChatConversationParticipant.objects.filter(conversation=conversation, user=request.user).first()
    if not participant:
        return render(request, "families/no_access.html", {"family": family})

    _mark_conversation_read(conversation, request.user)

    messages_qs = conversation.messages.filter(is_deleted=False).select_related(
        "author",
        "author__profile",
    ).prefetch_related(
        "read_receipts__user",
        "read_receipts__user__profile",
    ).order_by("-created_at")[:100]
    messages_data = [_serialize_conversation_message(message, request.user) for message in reversed(list(messages_qs))]

    participants = conversation.participants.select_related("user", "user__profile")
    return render(request, "families/conversation_room.html", {
        "family": family,
        "membership": membership,
        "conversation": conversation,
        "conversation_title": _conversation_title(conversation, request.user),
        "messages_data": messages_data,
        "participants": participants,
        "form": ConversationMessageForm(),
        "ws_path": f"/ws/families/{family.id}/conversations/{conversation.id}/",
    })


# ===========================
# Family Milestone CRUD
# ===========================

@login_required
def milestone_list(request, family_id):
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})

    milestones = FamilyMilestone.objects.filter(family=family).select_related("person", "event", "created_by")
    return render(request, "families/milestone_list.html", {
        "family": family,
        "membership": membership,
        "milestones": milestones.order_by("-date"),
    })


@login_required
def milestone_create(request, family_id):
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership or membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": None})

    if request.method == "POST":
        form = FamilyMilestoneForm(request.POST, request.FILES, family=family)
        if form.is_valid():
            milestone = form.save(commit=False)
            milestone.family = family
            milestone.created_by = request.user
            milestone.save()
            form.save_m2m()
            return redirect("families:milestone_list", family_id=family.id)
    else:
        form = FamilyMilestoneForm(family=family)

    return render(request, "families/milestone_form.html", {
        "family": family,
        "membership": membership,
        "form": form,
        "mode": "create",
    })


@login_required
def milestone_edit(request, family_id, milestone_id):
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership or membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": None})

    milestone = get_object_or_404(FamilyMilestone, id=milestone_id, family=family)
    if request.method == "POST":
        form = FamilyMilestoneForm(request.POST, request.FILES, instance=milestone, family=family)
        if form.is_valid():
            form.save()
            return redirect("families:milestone_list", family_id=family.id)
    else:
        form = FamilyMilestoneForm(instance=milestone, family=family)

    return render(request, "families/milestone_form.html", {
        "family": family,
        "membership": membership,
        "form": form,
        "mode": "edit",
        "milestone": milestone,
    })


@login_required
def milestone_delete(request, family_id, milestone_id):
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership or membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": None})

    milestone = get_object_or_404(FamilyMilestone, id=milestone_id, family=family)
    if request.method == "POST":
        milestone.delete()
        return redirect("families:milestone_list", family_id=family.id)

    return render(request, "families/milestone_delete.html", {
        "family": family,
        "membership": membership,
        "milestone": milestone,
    })


@login_required
def chat_room(request, family_id):
    """
    Legacy family chat route that now redirects into the unified conversation room.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    conversation = _get_or_create_family_conversation(family, request.user)
    return redirect("families:conversation_room", family_id=family.id, conversation_id=conversation.id)


@login_required
def conversation_message_delete(request, family_id, conversation_id, message_id):
    """
    Soft delete a unified conversation message.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)

    conversation = get_object_or_404(ChatConversation, id=conversation_id, family=family)
    message = get_object_or_404(ChatConversationMessage, id=message_id, conversation=conversation)

    can_delete = (
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN] or
        message.author == request.user
    )
    if not can_delete:
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "POST":
        message.is_deleted = True
        message.save(update_fields=["is_deleted", "updated_at"])
        return redirect("families:conversation_room", family_id=family.id, conversation_id=conversation.id)

    return JsonResponse({"error": "POST required"}, status=405)


@login_required
def chat_messages_json(request, family_id):
    """
    JSON endpoint for loading chat messages.
    Used for optional real-time polling or future WebSocket upgrades.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    # Get messages after a specific ID (for polling)
    after_id = request.GET.get('after', 0)
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0
    
    query = ChatMessage.objects.filter(
        family=family,
        is_deleted=False
    ).select_related('author')
    
    if after_id:
        query = query.filter(id__gt=after_id)
    
    messages_list = query.order_by('created_at')[:50]
    
    data = {
        "messages": [
            {
                "id": m.id,
                "author": m.author.email if m.author else "Deleted User",
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                "is_own": m.author == request.user if m.author else False,
            }
            for m in messages_list
        ]
    }
    
    return JsonResponse(data)


@login_required
def chat_delete_message(request, family_id, message_id):
    """
    Delete (soft delete) a chat message.
    Only author or admin/owner can delete.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return JsonResponse({"error": "Access denied"}, status=403)
    
    message = get_object_or_404(ChatMessage, id=message_id, family=family)
    
    can_delete = (
        membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN] or
        message.author == request.user
    )
    
    if not can_delete:
        return JsonResponse({"error": "Permission denied"}, status=403)
    
    if request.method == "POST":
        message.is_deleted = True
        message.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({"success": True})
        
        return redirect("families:chat_room", family_id=family.id)
    
    return JsonResponse({"error": "POST required"}, status=405)


# =============================================================================
# Phase 7: GEDCOM Import Report & Duplicate Review Views
# =============================================================================

@login_required
def gedcom_import_report(request, family_id, import_id):
    """
    Display import report with statistics and duplicate review queue.
    """
    from .models import GedcomImport, PotentialDuplicate
    import json
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    gedcom_import = get_object_or_404(
        GedcomImport,
        id=import_id,
        family=family
    )
    
    # Parse errors from JSON
    errors = json.loads(gedcom_import.errors) if gedcom_import.errors else []
    
    # Get pending duplicates
    pending_duplicates = PotentialDuplicate.objects.filter(
        gedcom_import=gedcom_import,
        status=PotentialDuplicate.Status.PENDING
    ).select_related('existing_person', 'imported_person')[:20]
    
    # Count duplicates by status
    duplicate_stats = {
        'pending': PotentialDuplicate.objects.filter(
            gedcom_import=gedcom_import,
            status=PotentialDuplicate.Status.PENDING
        ).count(),
        'merged': PotentialDuplicate.objects.filter(
            gedcom_import=gedcom_import,
            status=PotentialDuplicate.Status.MERGED
        ).count(),
        'kept_both': PotentialDuplicate.objects.filter(
            gedcom_import=gedcom_import,
            status=PotentialDuplicate.Status.KEPT_BOTH
        ).count(),
    }
    
    return render(request, "families/gedcom_import_report.html", {
        "family": family,
        "membership": membership,
        "gedcom_import": gedcom_import,
        "errors": errors,
        "pending_duplicates": pending_duplicates,
        "duplicate_stats": duplicate_stats,
    })


@login_required
def gedcom_import_history(request, family_id):
    """
    Display history of all GEDCOM imports for a family.
    """
    from .models import GedcomImport
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    imports = GedcomImport.objects.filter(family=family).order_by('-created_at')
    
    return render(request, "families/gedcom_import_history.html", {
        "family": family,
        "membership": membership,
        "imports": imports,
    })


@login_required
def gedcom_import_rollback(request, family_id, import_id):
    """
    Rollback (delete) all persons created by a specific GEDCOM import.
    This is useful if the wrong file was uploaded.
    """
    from .models import GedcomImport, Person, PotentialDuplicate
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can rollback imports
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.error(request, "Only administrators can rollback imports.")
        return redirect('families:gedcom_import_report', family_id=family_id, import_id=import_id)
    
    gedcom_import = get_object_or_404(
        GedcomImport,
        id=import_id,
        family=family
    )
    
    # Get persons created by this import
    imported_persons = Person.objects.filter(source_import=gedcom_import)
    person_count = imported_persons.count()
    
    if request.method == "POST":
        if request.POST.get('confirm') == 'yes':
            # Delete all potential duplicates for this import
            PotentialDuplicate.objects.filter(gedcom_import=gedcom_import).delete()
            
            # Delete all persons created by this import
            deleted_count = imported_persons.delete()[0]
            
            # Update the import status
            gedcom_import.status = GedcomImport.Status.CANCELLED
            gedcom_import.save()
            
            messages.success(request, f"Rollback complete. {deleted_count} persons deleted.")
            return redirect('families:gedcom_import_history', family_id=family_id)
        else:
            messages.info(request, "Rollback cancelled.")
            return redirect('families:gedcom_import_report', family_id=family_id, import_id=import_id)
    
    return render(request, "families/gedcom_import_rollback.html", {
        "family": family,
        "membership": membership,
        "gedcom_import": gedcom_import,
        "person_count": person_count,
        "imported_persons": imported_persons[:20],  # Show first 20 for preview
    })


@login_required
def gedcom_import_delete(request, family_id, import_id):
    """
    Permanently delete a GEDCOM import record.
    Only works on cancelled imports (already rolled back).
    """
    from .models import GedcomImport
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can delete imports
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.error(request, "Only administrators can delete import records.")
        return redirect('families:gedcom_import_history', family_id=family_id)
    
    gedcom_import = get_object_or_404(
        GedcomImport,
        id=import_id,
        family=family
    )
    
    # Only allow deleting cancelled imports
    if gedcom_import.status != GedcomImport.Status.CANCELLED:
        messages.error(request, "You can only delete cancelled imports. Rollback the import first.")
        return redirect('families:gedcom_import_report', family_id=family_id, import_id=import_id)
    
    if request.method == "POST":
        file_name = gedcom_import.file_name
        gedcom_import.delete()
        messages.success(request, f"Import record '{file_name}' permanently deleted.")
        return redirect('families:gedcom_import_history', family_id=family_id)
    
    return render(request, "families/gedcom_import_delete.html", {
        "family": family,
        "membership": membership,
        "gedcom_import": gedcom_import,
    })


@login_required
def duplicate_review(request, family_id, duplicate_id):
    """
    Review a potential duplicate and choose action.
    """
    from .models import GedcomImport, PotentialDuplicate
    from .gedcom import merge_persons
    import json
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can review duplicates
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    duplicate = get_object_or_404(
        PotentialDuplicate,
        id=duplicate_id,
        gedcom_import__family=family
    )
    
    # Parse match reasons
    match_reasons = json.loads(duplicate.match_reasons) if duplicate.match_reasons else []
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'merge_keep_existing':
            # Keep existing, merge imported into it
            # Update duplicate status BEFORE merge (merge deletes the imported_person)
            existing_name = duplicate.existing_person.full_name
            PotentialDuplicate.objects.filter(id=duplicate.id).update(
                status=PotentialDuplicate.Status.MERGED,
                reviewed_by=request.user,
                reviewed_at=timezone.now()
            )
            merge_persons(duplicate.existing_person, duplicate.imported_person, request.user)
            messages.success(request, f"Merged into {existing_name}")
            
        elif action == 'merge_keep_imported':
            # Keep imported, merge existing into it
            # Update duplicate status BEFORE merge (merge deletes the existing_person)
            PotentialDuplicate.objects.filter(id=duplicate.id).update(
                status=PotentialDuplicate.Status.MERGED,
                reviewed_by=request.user,
                reviewed_at=timezone.now()
            )
            merge_persons(duplicate.imported_person, duplicate.existing_person, request.user)
            messages.success(request, "Merged into imported record")
            
        elif action == 'keep_both':
            # Keep both as separate records
            duplicate.status = PotentialDuplicate.Status.KEPT_BOTH
            duplicate.reviewed_by = request.user
            duplicate.reviewed_at = timezone.now()
            duplicate.save()
            messages.success(request, "Both records kept as separate people")
            
        elif action == 'dismiss':
            # Dismiss without action
            duplicate.status = PotentialDuplicate.Status.DISMISSED
            duplicate.reviewed_by = request.user
            duplicate.reviewed_at = timezone.now()
            duplicate.save()
            messages.info(request, "Duplicate dismissed")
        
        # Redirect to import report
        return redirect("families:gedcom_import_report", 
                       family_id=family.id, 
                       import_id=duplicate.gedcom_import.id)
    
    return render(request, "families/duplicate_review.html", {
        "family": family,
        "membership": membership,
        "duplicate": duplicate,
        "match_reasons": match_reasons,
    })


@login_required
def duplicate_queue(request, family_id):
    """
    Display all pending duplicates across all imports for a family.
    """
    from .models import PotentialDuplicate
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    duplicates = PotentialDuplicate.objects.filter(
        gedcom_import__family=family,
        status=PotentialDuplicate.Status.PENDING
    ).select_related('existing_person', 'imported_person', 'gedcom_import').order_by('-confidence_score')
    
    # Count 100% confidence duplicates
    perfect_duplicates_count = duplicates.filter(confidence_score=100).count()
    
    return render(request, "families/duplicate_queue.html", {
        "family": family,
        "membership": membership,
        "duplicates": duplicates,
        "perfect_duplicates_count": perfect_duplicates_count,
    })


@login_required
def bulk_delete_perfect_duplicates(request, family_id):
    """
    Bulk delete all 100% confidence duplicates by removing the imported person
    and marking the duplicate as merged.
    """
    from .models import PotentialDuplicate
    
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can bulk delete
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.error(request, "Only administrators can perform bulk operations.")
        return redirect('families:duplicate_queue', family_id=family_id)
    
    if request.method == "POST":
        # Get all 100% confidence duplicates - convert to list to avoid iteration issues
        perfect_duplicates = list(PotentialDuplicate.objects.filter(
            gedcom_import__family=family,
            status=PotentialDuplicate.Status.PENDING,
            confidence_score=100
        ).select_related('existing_person', 'imported_person'))
        
        deleted_count = 0
        for dup in perfect_duplicates:
            # Delete the imported person (keep the existing one)
            # The CASCADE on the model will automatically delete the duplicate record
            if dup.imported_person:
                dup.imported_person.delete()
                deleted_count += 1
        
        messages.success(request, f"Successfully removed {deleted_count} identical duplicates.")
        return redirect('families:duplicate_queue', family_id=family_id)
    
    # GET request - show confirmation
    perfect_duplicates = PotentialDuplicate.objects.filter(
        gedcom_import__family=family,
        status=PotentialDuplicate.Status.PENDING,
        confidence_score=100
    ).select_related('existing_person', 'imported_person')[:20]
    
    total_count = PotentialDuplicate.objects.filter(
        gedcom_import__family=family,
        status=PotentialDuplicate.Status.PENDING,
        confidence_score=100
    ).count()
    
    return render(request, "families/bulk_delete_duplicates.html", {
        "family": family,
        "membership": membership,
        "perfect_duplicates": perfect_duplicates,
        "total_count": total_count,
    })


# =============================================================================
# Phase 8: DNA Assist Tools Views
# =============================================================================

@login_required
def dna_kit_list(request):
    """
    List all DNA kits owned by the current user.
    
    This is the main DNA dashboard showing the user's kits,
    recent matches, and pending suggestions.
    
    Supports ?link_to=<person_id>&family=<family_id> to pre-select a person to link.
    """
    from .models import DNAKit, DNAMatch, RelationshipSuggestion, Person, FamilySpace
    
    kits = DNAKit.objects.filter(user=request.user).order_by('-uploaded_at')
    
    # Get recent matches for user's kits
    kit_ids = kits.values_list('id', flat=True)
    recent_matches = DNAMatch.objects.filter(
        Q(kit1_id__in=kit_ids) | Q(kit2_id__in=kit_ids)
    ).select_related('kit1', 'kit2').order_by('-discovered_at')[:10]
    
    # Count pending suggestions
    pending_suggestions = RelationshipSuggestion.objects.filter(
        suggested_for_kit__in=kits,
        status=RelationshipSuggestion.Status.PENDING
    ).count()
    
    # Handle link_to parameter (from person profile page)
    link_to_person = None
    link_to_family = None
    if 'link_to' in request.GET:
        try:
            person_id = int(request.GET.get('link_to'))
            link_to_person = Person.objects.get(id=person_id, is_deleted=False)
            # Also get family if provided
            if 'family' in request.GET:
                family_id = int(request.GET.get('family'))
                link_to_family = FamilySpace.objects.get(id=family_id)
        except (ValueError, Person.DoesNotExist, FamilySpace.DoesNotExist):
            pass
    
    return render(request, "families/dna_kit_list.html", {
        "kits": kits,
        "recent_matches": recent_matches,
        "pending_suggestions": pending_suggestions,
        "link_to_person": link_to_person,
        "link_to_family": link_to_family,
    })


@login_required
def dna_kit_create(request):
    """
    Register a new DNA kit.
    
    Supports ?link_to=<person_id>&family=<family_id> to pre-link the kit after creation.
    """
    from .forms import DNAKitForm
    from .models import DNAKit, Person, FamilySpace
    
    # Check for link_to parameter
    link_to_person = None
    link_to_family = None
    if 'link_to' in request.GET:
        try:
            person_id = int(request.GET.get('link_to'))
            link_to_person = Person.objects.get(id=person_id, is_deleted=False)
            if 'family' in request.GET:
                family_id = int(request.GET.get('family'))
                link_to_family = FamilySpace.objects.get(id=family_id)
        except (ValueError, Person.DoesNotExist, FamilySpace.DoesNotExist):
            pass
    
    if request.method == "POST":
        form = DNAKitForm(request.POST)
        if form.is_valid():
            kit = form.save(commit=False)
            kit.user = request.user
            # Auto-link to person if specified
            link_person_id = request.POST.get('link_to_person')
            if link_person_id:
                try:
                    kit.linked_person = Person.objects.get(id=link_person_id, is_deleted=False)
                except Person.DoesNotExist:
                    pass
            kit.save()
            messages.success(request, f"DNA kit '{kit.display_name}' registered successfully!")
            # Redirect back to person profile if we linked to them
            if kit.linked_person and link_to_family:
                return redirect("families:person_detail", family_id=link_to_family.id, person_id=kit.linked_person.id)
            return redirect("families:dna_kit_list")
    else:
        form = DNAKitForm()
    
    return render(request, "families/dna_kit_create.html", {
        "form": form,
        "link_to_person": link_to_person,
        "link_to_family": link_to_family,
    })


@login_required
def dna_kit_detail(request, kit_id):
    """
    View details of a DNA kit and its matches.
    """
    from .models import DNAKit, DNAMatch
    
    kit = get_object_or_404(DNAKit, id=kit_id)
    
    # Only owner can view their kit details
    if kit.user != request.user:
        messages.error(request, "You don't have access to this DNA kit.")
        return redirect("families:dna_kit_list")
    
    # Get all matches for this kit
    matches = DNAMatch.objects.filter(
        Q(kit1=kit) | Q(kit2=kit)
    ).select_related('kit1', 'kit2', 'kit1__user', 'kit2__user').order_by('-shared_cm')
    
    return render(request, "families/dna_kit_detail.html", {
        "kit": kit,
        "matches": matches,
    })


@login_required
def dna_kit_edit(request, kit_id):
    """
    Edit a DNA kit.
    """
    from .forms import DNAKitForm
    from .models import DNAKit
    
    kit = get_object_or_404(DNAKit, id=kit_id, user=request.user)
    
    if request.method == "POST":
        form = DNAKitForm(request.POST, instance=kit)
        if form.is_valid():
            form.save()
            messages.success(request, f"DNA kit '{kit.display_name}' updated.")
            return redirect("families:dna_kit_detail", kit_id=kit.id)
    else:
        form = DNAKitForm(instance=kit)
    
    return render(request, "families/dna_kit_edit.html", {
        "form": form,
        "kit": kit,
    })


@login_required
def dna_kit_delete(request, kit_id):
    """
    Delete a DNA kit.
    """
    from .models import DNAKit
    
    kit = get_object_or_404(DNAKit, id=kit_id, user=request.user)
    
    if request.method == "POST":
        name = kit.display_name
        kit.delete()
        messages.success(request, f"DNA kit '{name}' deleted.")
        return redirect("families:dna_kit_list")
    
    return render(request, "families/dna_kit_delete.html", {
        "kit": kit,
    })


@login_required
def dna_match_list(request):
    """
    List all DNA matches for the current user's kits.
    """
    from .models import DNAKit, DNAMatch
    
    kits = DNAKit.objects.filter(user=request.user)
    kit_ids = kits.values_list('id', flat=True)
    
    matches = DNAMatch.objects.filter(
        Q(kit1_id__in=kit_ids) | Q(kit2_id__in=kit_ids)
    ).select_related('kit1', 'kit2', 'kit1__user', 'kit2__user').order_by('-shared_cm')
    
    return render(request, "families/dna_match_list.html", {
        "matches": matches,
        "kits": kits,
    })


@login_required
def dna_match_create(request, kit_id):
    """
    Add a new DNA match manually.
    
    Users can add matches they've found on other platforms.
    """
    from .forms import DNAMatchForm
    from .models import DNAKit, DNAMatch
    
    kit = get_object_or_404(DNAKit, id=kit_id, user=request.user)
    
    # Get other kits that allow matching (not the user's own kits)
    other_kits = DNAKit.objects.filter(
        allow_matching=True
    ).exclude(user=request.user).select_related('user')
    
    if request.method == "POST":
        form = DNAMatchForm(request.POST)
        other_kit_id = request.POST.get('other_kit_id')
        
        if form.is_valid() and other_kit_id:
            try:
                other_kit = DNAKit.objects.get(id=other_kit_id, allow_matching=True)
                
                # Check if match already exists
                existing = DNAMatch.objects.filter(
                    Q(kit1=kit, kit2=other_kit) |
                    Q(kit1=other_kit, kit2=kit)
                ).first()
                
                if existing:
                    messages.warning(request, "A match between these kits already exists.")
                    return redirect("families:dna_match_detail", match_id=existing.id)
                
                match = form.save(commit=False)
                match.kit1 = kit
                match.kit2 = other_kit
                match.confirmed_by_kit1 = True
                match.save()
                
                # Create relationship suggestion
                _create_relationship_suggestion(match, kit)
                
                messages.success(request, f"DNA match added! Predicted: {match.predicted_relationship}")
                return redirect("families:dna_match_detail", match_id=match.id)
                
            except DNAKit.DoesNotExist:
                messages.error(request, "Selected kit not found or doesn't allow matching.")
    else:
        form = DNAMatchForm()
    
    return render(request, "families/dna_match_create.html", {
        "form": form,
        "kit": kit,
        "other_kits": other_kits,
    })


def _create_relationship_suggestion(match, for_kit):
    """
    Helper to create relationship suggestions from a DNA match.
    """
    from .models import RelationshipSuggestion, FamilySpace, Membership
    
    # Find families where the kit owner is a member
    memberships = Membership.objects.filter(user=for_kit.user)
    
    for membership in memberships:
        # Create a suggestion for each family
        RelationshipSuggestion.objects.get_or_create(
            dna_match=match,
            suggested_for_kit=for_kit,
            family=membership.family,
            defaults={
                'suggested_relationship': match.predicted_relationship,
            }
        )


@login_required
def dna_match_detail(request, match_id):
    """
    View details of a DNA match.
    """
    from .models import DNAKit, DNAMatch, RelationshipSuggestion
    
    match = get_object_or_404(
        DNAMatch.objects.select_related('kit1', 'kit2', 'kit1__user', 'kit2__user'),
        id=match_id
    )
    
    # Check if user owns either kit
    user_kits = DNAKit.objects.filter(user=request.user)
    if match.kit1 not in user_kits and match.kit2 not in user_kits:
        messages.error(request, "You don't have access to this match.")
        return redirect("families:dna_match_list")
    
    # Get the user's kit in this match
    user_kit = match.kit1 if match.kit1.user == request.user else match.kit2
    other_kit = match.kit2 if match.kit1.user == request.user else match.kit1
    
    # Get suggestions for this match
    suggestions = RelationshipSuggestion.objects.filter(
        dna_match=match,
        suggested_for_kit=user_kit
    ).select_related('family', 'suggested_person')
    
    return render(request, "families/dna_match_detail.html", {
        "match": match,
        "user_kit": user_kit,
        "other_kit": other_kit,
        "suggestions": suggestions,
    })


@login_required
def dna_match_confirm(request, match_id):
    """
    Confirm a DNA match from the user's side.
    """
    from .models import DNAKit, DNAMatch
    
    match = get_object_or_404(DNAMatch, id=match_id)
    
    # Check if user owns either kit
    if match.kit1.user == request.user:
        match.confirmed_by_kit1 = True
        match.save()
        messages.success(request, "You've confirmed this DNA match.")
    elif match.kit2.user == request.user:
        match.confirmed_by_kit2 = True
        match.save()
        messages.success(request, "You've confirmed this DNA match.")
    else:
        messages.error(request, "You cannot confirm this match.")
    
    return redirect("families:dna_match_detail", match_id=match.id)


@login_required
def relationship_suggestion_list(request):
    """
    List all pending relationship suggestions for the user.
    """
    from .models import DNAKit, RelationshipSuggestion
    
    kits = DNAKit.objects.filter(user=request.user)
    
    suggestions = RelationshipSuggestion.objects.filter(
        suggested_for_kit__in=kits
    ).select_related(
        'dna_match', 'dna_match__kit1', 'dna_match__kit2',
        'suggested_for_kit', 'suggested_person', 'family'
    ).order_by('status', '-created_at')
    
    pending = suggestions.filter(status=RelationshipSuggestion.Status.PENDING)
    resolved = suggestions.exclude(status=RelationshipSuggestion.Status.PENDING)
    
    return render(request, "families/relationship_suggestion_list.html", {
        "pending_suggestions": pending,
        "resolved_suggestions": resolved,
    })


@login_required
def relationship_suggestion_review(request, suggestion_id):
    """
    Review a relationship suggestion and link to tree if accepted.
    
    This is the attach-to-tree confirmation workflow.
    """
    from .forms import LinkToTreeForm
    from .models import DNAKit, RelationshipSuggestion, Person, Relationship
    
    suggestion = get_object_or_404(
        RelationshipSuggestion.objects.select_related(
            'dna_match', 'dna_match__kit1', 'dna_match__kit2',
            'suggested_for_kit', 'family'
        ),
        id=suggestion_id,
        suggested_for_kit__user=request.user
    )
    
    # Get the other kit in the match
    match = suggestion.dna_match
    other_kit = match.kit2 if match.kit1 == suggestion.suggested_for_kit else match.kit1
    
    # Get family membership
    family = suggestion.family
    membership = Membership.objects.filter(
        family=family,
        user=request.user
    ).first()
    
    if not membership:
        messages.error(request, "You don't have access to this family.")
        return redirect("families:relationship_suggestion_list")
    
    # Get possible people to link to
    people = Person.objects.filter(family=family).order_by('last_name', 'first_name')
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'accept':
            form = LinkToTreeForm(request.POST)
            
            person_id = request.POST.get('person_id')
            create_new = request.POST.get('create_new') == 'true'
            
            if create_new:
                # Create a new person for this match
                new_person = Person.objects.create(
                    family=family,
                    first_name=other_kit.display_name.split()[0] if ' ' in other_kit.display_name else 'Unknown',
                    last_name='(DNA Match)',
                    created_by=request.user,
                )
                # Link the other kit to this person
                if other_kit.linked_person is None:
                    other_kit.linked_person = new_person
                    other_kit.save()
                
                suggestion.suggested_person = new_person
                suggestion.status = RelationshipSuggestion.Status.ACCEPTED
                suggestion.reviewed_by = request.user
                suggestion.reviewed_at = timezone.now()
                suggestion.save()
                
                messages.success(request, f"Created new person and linked to DNA match!")
                return redirect("families:person_detail", family_id=family.id, person_id=new_person.id)
                
            elif person_id:
                try:
                    person = Person.objects.get(id=person_id, family=family)
                    
                    # Link the other kit to this person if not already linked
                    if other_kit.linked_person is None:
                        other_kit.linked_person = person
                        other_kit.save()
                    
                    suggestion.suggested_person = person
                    suggestion.status = RelationshipSuggestion.Status.ACCEPTED
                    suggestion.reviewed_by = request.user
                    suggestion.reviewed_at = timezone.now()
                    suggestion.notes = request.POST.get('notes', '')
                    suggestion.save()
                    
                    messages.success(request, f"DNA match linked to {person.full_name}!")
                    return redirect("families:person_detail", family_id=family.id, person_id=person.id)
                    
                except Person.DoesNotExist:
                    messages.error(request, "Selected person not found.")
            else:
                messages.warning(request, "Please select a person or create a new one.")
                
        elif action == 'reject':
            suggestion.status = RelationshipSuggestion.Status.REJECTED
            suggestion.reviewed_by = request.user
            suggestion.reviewed_at = timezone.now()
            suggestion.notes = request.POST.get('notes', '')
            suggestion.save()
            messages.info(request, "Suggestion rejected.")
            return redirect("families:relationship_suggestion_list")
            
        elif action == 'ignore':
            suggestion.status = RelationshipSuggestion.Status.IGNORED
            suggestion.reviewed_by = request.user
            suggestion.reviewed_at = timezone.now()
            suggestion.save()
            messages.info(request, "Suggestion ignored.")
            return redirect("families:relationship_suggestion_list")
    
    form = LinkToTreeForm()
    
    return render(request, "families/relationship_suggestion_review.html", {
        "suggestion": suggestion,
        "match": match,
        "other_kit": other_kit,
        "family": family,
        "people": people,
        "form": form,
    })


@login_required
def dna_link_to_person(request, kit_id, family_id):
    """
    Link a DNA kit to a person in a family tree.
    
    Supports ?person=<id> to pre-select the person.
    """
    from .models import DNAKit, Person
    
    kit = get_object_or_404(DNAKit, id=kit_id, user=request.user)
    family, membership = _get_membership_or_deny(request, family_id)
    
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    people = Person.objects.filter(family=family, is_deleted=False).order_by('last_name', 'first_name')
    
    # Pre-select person from query param
    selected_person_id = request.GET.get('person')
    
    if request.method == "POST":
        person_id = request.POST.get('person_id')
        if person_id:
            try:
                person = Person.objects.get(id=person_id, family=family, is_deleted=False)
                kit.linked_person = person
                kit.save()
                messages.success(request, f"DNA kit linked to {person.full_name}")
                return redirect("families:person_detail", family_id=family.id, person_id=person.id)
            except Person.DoesNotExist:
                messages.error(request, "Person not found.")
    
    return render(request, "families/dna_link_to_person.html", {
        "kit": kit,
        "family": family,
        "people": people,
        "selected_person_id": selected_person_id,
    })


@login_required
def dna_connections(request):
    """
    Interactive network visualization of DNA connections.
    
    Shows a force-directed graph of DNA matches between kits,
    with nodes representing people/kits and edges representing
    genetic connections (weighted by cM).
    """
    from .models import DNAKit, DNAMatch, Person
    import json
    
    # Get user's kits
    user_kits = DNAKit.objects.filter(user=request.user)
    user_kit_ids = set(user_kits.values_list('id', flat=True))
    
    if not user_kits.exists():
        return render(request, "families/dna_connections.html", {
            "nodes_json": "[]",
            "links_json": "[]",
            "has_data": False,
        })
    
    # Get all matches involving user's kits
    matches = DNAMatch.objects.filter(
        Q(kit1_id__in=user_kit_ids) | Q(kit2_id__in=user_kit_ids)
    ).select_related(
        'kit1', 'kit2', 'kit1__user', 'kit2__user',
        'kit1__linked_person', 'kit2__linked_person'
    )
    
    # Build nodes and links for D3.js
    nodes = {}
    links = []
    
    # Add user's own kits as nodes
    for kit in user_kits:
        node_id = f"kit_{kit.id}"
        person_name = kit.linked_person.full_name if kit.linked_person else None
        nodes[node_id] = {
            "id": node_id,
            "kit_id": kit.id,
            "name": person_name or kit.display_name,
            "display_name": kit.display_name,
            "provider": kit.get_provider_display(),
            "is_own": True,
            "linked_person_id": kit.linked_person.id if kit.linked_person else None,
            "linked_person_family_id": kit.linked_person.family_id if kit.linked_person else None,
            "user_name": kit.user.get_full_name() or kit.user.username,
        }
    
    # Add matches and connected kits
    for match in matches:
        kit1_id = f"kit_{match.kit1_id}"
        kit2_id = f"kit_{match.kit2_id}"
        
        # Add kit1 if not already present
        if kit1_id not in nodes:
            kit = match.kit1
            person_name = kit.linked_person.full_name if kit.linked_person else None
            nodes[kit1_id] = {
                "id": kit1_id,
                "kit_id": kit.id,
                "name": person_name or kit.display_name,
                "display_name": kit.display_name,
                "provider": kit.get_provider_display(),
                "is_own": kit.id in user_kit_ids,
                "linked_person_id": kit.linked_person.id if kit.linked_person else None,
                "linked_person_family_id": kit.linked_person.family_id if kit.linked_person else None,
                "user_name": kit.user.get_full_name() or kit.user.username,
            }
        
        # Add kit2 if not already present
        if kit2_id not in nodes:
            kit = match.kit2
            person_name = kit.linked_person.full_name if kit.linked_person else None
            nodes[kit2_id] = {
                "id": kit2_id,
                "kit_id": kit.id,
                "name": person_name or kit.display_name,
                "display_name": kit.display_name,
                "provider": kit.get_provider_display(),
                "is_own": kit.id in user_kit_ids,
                "linked_person_id": kit.linked_person.id if kit.linked_person else None,
                "linked_person_family_id": kit.linked_person.family_id if kit.linked_person else None,
                "user_name": kit.user.get_full_name() or kit.user.username,
            }
        
        # Calculate link strength based on cM (closer = stronger)
        # cM ranges: 3400+ parent/sibling, 200-900 extended, <200 distant
        cm = match.shared_cm
        if cm >= 900:
            strength = "close"
            width = 6
        elif cm >= 200:
            strength = "extended"
            width = 4
        else:
            strength = "distant"
            width = 2
        
        links.append({
            "source": kit1_id,
            "target": kit2_id,
            "match_id": match.id,
            "shared_cm": match.shared_cm,
            "predicted_relationship": match.predicted_relationship,
            "is_confirmed": match.is_confirmed,
            "strength": strength,
            "width": width,
        })
    
    return render(request, "families/dna_connections.html", {
        "nodes_json": json.dumps(list(nodes.values())),
        "links_json": json.dumps(links),
        "has_data": len(links) > 0,
        "total_kits": len(nodes),
        "total_matches": len(links),
    })


# =============================================================================
# Phase 9: Trash Bin, Restore, and Audit Trail Views
# =============================================================================

@login_required
def trash_bin(request, family_id):
    """
    View deleted items (persons and relationships) that can be restored.
    
    Only admins/owners can access trash.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only admin/owner can view trash
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    deleted_persons = Person.objects.filter(family=family, is_deleted=True).order_by('-deleted_at')
    deleted_relationships = Relationship.objects.filter(
        family=family, 
        is_deleted=True,
        # Don't show relationships where either person is also deleted
        person1__is_deleted=False,
        person2__is_deleted=False
    ).order_by('-deleted_at')
    
    return render(request, "families/trash_bin.html", {
        "family": family,
        "membership": membership,
        "deleted_persons": deleted_persons,
        "deleted_relationships": deleted_relationships,
    })


@login_required
def restore_person(request, family_id, person_id):
    """
    Restore a soft-deleted person.
    
    Only admins/owners can restore.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    person = get_object_or_404(Person, id=person_id, family=family, is_deleted=True)
    
    if request.method == "POST":
        person.restore()
        
        # Create audit log
        AuditLog.log(
            family=family,
            user=request.user,
            action=AuditLog.Action.RESTORE,
            obj=person,
            request=request
        )
        
        messages.success(request, f"{person.full_name} has been restored.")
        return redirect("families:trash_bin", family_id=family.id)
    
    return render(request, "families/restore_confirm.html", {
        "family": family,
        "membership": membership,
        "item": person,
        "item_type": "Person",
    })


@login_required
def restore_relationship(request, family_id, relationship_id):
    """
    Restore a soft-deleted relationship.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    rel = get_object_or_404(Relationship, id=relationship_id, family=family, is_deleted=True)
    
    if request.method == "POST":
        rel.restore()
        
        # Create audit log
        AuditLog.log(
            family=family,
            user=request.user,
            action=AuditLog.Action.RESTORE,
            obj=rel,
            request=request
        )
        
        messages.success(request, "Relationship has been restored.")
        return redirect("families:trash_bin", family_id=family.id)
    
    return render(request, "families/restore_confirm.html", {
        "family": family,
        "membership": membership,
        "item": rel,
        "item_type": "Relationship",
    })


@login_required
def permanent_delete_person(request, family_id, person_id):
    """
    Permanently delete a person (only owner can do this).
    
    This action cannot be undone.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Only owner can permanently delete
    if membership.role != Membership.Role.OWNER:
        messages.error(request, "Only the family owner can permanently delete records.")
        return redirect("families:trash_bin", family_id=family.id)
    
    person = get_object_or_404(Person, id=person_id, family=family, is_deleted=True)
    
    if request.method == "POST":
        person_name = person.full_name
        
        # Store data before permanent deletion
        previous_data = {
            'first_name': person.first_name,
            'last_name': person.last_name,
            'maiden_name': person.maiden_name,
            'gender': person.gender,
            'birth_date': str(person.birth_date) if person.birth_date else None,
            'death_date': str(person.death_date) if person.death_date else None,
        }
        
        # Create audit log before deletion
        AuditLog.objects.create(
            family=family,
            user=request.user,
            action=AuditLog.Action.DELETE,
            object_type=AuditLog.ObjectType.PERSON,
            object_id=person.id,
            object_repr=f"PERMANENT: {person_name}",
            previous_data=previous_data,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
        )
        
        # Permanently delete
        person.delete()
        
        messages.success(request, f"{person_name} has been permanently deleted.")
        return redirect("families:trash_bin", family_id=family.id)
    
    return render(request, "families/permanent_delete_confirm.html", {
        "family": family,
        "membership": membership,
        "item": person,
        "item_type": "Person",
    })


@login_required
def audit_log(request, family_id):
    """
    View audit trail for family data changes.
    
    Only admins/owners can view the audit log.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    # Filter options
    action_filter = request.GET.get('action', '')
    object_type_filter = request.GET.get('type', '')
    
    logs = AuditLog.objects.filter(family=family).select_related('user')
    
    if action_filter:
        logs = logs.filter(action=action_filter)
    if object_type_filter:
        logs = logs.filter(object_type=object_type_filter)
    
    logs = logs[:100]  # Limit to last 100 entries
    
    return render(request, "families/audit_log.html", {
        "family": family,
        "membership": membership,
        "logs": logs,
        "actions": AuditLog.Action.choices,
        "object_types": AuditLog.ObjectType.choices,
        "current_action": action_filter,
        "current_type": object_type_filter,
    })


@login_required
def deletion_request_create(request, family_id, object_type, object_id):
    """
    Request deletion of a critical item (requires approval).
    
    For members who aren't admin/owner but need something deleted.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    # Viewers cannot request deletions
    if membership.role == Membership.Role.VIEWER:
        return render(request, "families/no_access.html", {"family": family})
    
    # Get the object
    obj = None
    obj_repr = ""
    obj_data = {}
    
    if object_type == 'person':
        obj = get_object_or_404(Person, id=object_id, family=family, is_deleted=False)
        obj_repr = obj.full_name
        obj_data = {
            'name': obj.full_name,
            'birth_date': str(obj.birth_date) if obj.birth_date else None,
            'death_date': str(obj.death_date) if obj.death_date else None,
        }
        db_type = DeletionRequest.ObjectType.PERSON
    elif object_type == 'relationship':
        obj = get_object_or_404(Relationship, id=object_id, family=family, is_deleted=False)
        obj_repr = str(obj)
        obj_data = {
            'person1': str(obj.person1),
            'person2': str(obj.person2),
            'type': obj.relationship_type,
        }
        db_type = DeletionRequest.ObjectType.RELATIONSHIP
    else:
        messages.error(request, "Invalid object type.")
        return redirect("families:family_detail", family_id=family.id)
    
    if request.method == "POST":
        reason = request.POST.get('reason', '')
        
        # Create the deletion request
        del_request = DeletionRequest.objects.create(
            family=family,
            requester=request.user,
            object_type=db_type,
            object_id=object_id,
            object_repr=obj_repr,
            object_data=obj_data,
            reason=reason,
        )
        
        # Notify admins
        admins = Membership.objects.filter(
            family=family,
            role__in=[Membership.Role.OWNER, Membership.Role.ADMIN]
        ).exclude(user=request.user)
        
        for admin_membership in admins:
            create_notification(
                user=admin_membership.user,
                family=family,
                notification_type='mention',
                message=f"{request.user.get_full_name() or request.user.username} requested deletion of {obj_repr}",
                link=f"/families/{family.id}/deletion-requests/"
            )
        
        messages.success(request, "Your deletion request has been submitted for review.")
        return redirect("families:my_deletion_requests", family_id=family.id)
    
    return render(request, "families/deletion_request_create.html", {
        "family": family,
        "membership": membership,
        "object": obj,
        "object_type": object_type,
    })


@login_required
def deletion_request_list(request, family_id):
    """
    List pending deletion requests (for admins/owners).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    pending = DeletionRequest.objects.filter(
        family=family,
        status=DeletionRequest.Status.PENDING
    ).select_related('requester')
    
    reviewed = DeletionRequest.objects.filter(
        family=family
    ).exclude(status=DeletionRequest.Status.PENDING).select_related('requester', 'reviewer')[:20]
    
    return render(request, "families/deletion_request_list.html", {
        "family": family,
        "membership": membership,
        "pending_requests": pending,
        "reviewed_requests": reviewed,
    })


@login_required
def my_deletion_requests(request, family_id):
    """
    View user's own deletion requests.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    my_requests = DeletionRequest.objects.filter(
        family=family,
        requester=request.user
    ).select_related('reviewer')
    
    return render(request, "families/my_deletion_requests.html", {
        "family": family,
        "membership": membership,
        "requests": my_requests,
    })


@login_required
def deletion_request_review(request, family_id, request_id):
    """
    Review (approve/reject) a deletion request.
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    if membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return render(request, "families/no_access.html", {"family": family})
    
    del_request = get_object_or_404(
        DeletionRequest, 
        id=request_id, 
        family=family,
        status=DeletionRequest.Status.PENDING
    )
    
    if request.method == "POST":
        action = request.POST.get('action')
        notes = request.POST.get('notes', '')
        
        if action == 'approve':
            del_request.approve(reviewer=request.user, notes=notes)
            
            # Create audit log
            AuditLog.objects.create(
                family=family,
                user=request.user,
                action=AuditLog.Action.DELETE,
                object_type=del_request.object_type,
                object_id=del_request.object_id,
                object_repr=f"APPROVED REQUEST: {del_request.object_repr}",
                previous_data=del_request.object_data,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
            )
            
            messages.success(request, f"Deletion request approved. {del_request.object_repr} has been moved to trash.")
        elif action == 'reject':
            del_request.reject(reviewer=request.user, notes=notes)
            messages.info(request, "Deletion request rejected.")
        
        # Notify requester
        create_notification(
            user=del_request.requester,
            family=family,
            notification_type='mention',
            message=f"Your deletion request for {del_request.object_repr} was {action}ed",
            link=f"/families/{family.id}/my-deletion-requests/"
        )
        
        return redirect("families:deletion_request_list", family_id=family.id)
    
    return render(request, "families/deletion_request_review.html", {
        "family": family,
        "membership": membership,
        "del_request": del_request,
    })


@login_required
def empty_trash(request, family_id):
    """
    Permanently delete all items in trash (owner only).
    """
    family, membership = _get_membership_or_deny(request, family_id)
    if not membership:
        return render(request, "families/no_access.html", {"family": None})
    
    if membership.role != Membership.Role.OWNER:
        messages.error(request, "Only the family owner can empty the trash.")
        return redirect("families:trash_bin", family_id=family.id)
    
    if request.method == "POST":
        # Count items
        person_count = Person.objects.filter(family=family, is_deleted=True).count()
        rel_count = Relationship.objects.filter(family=family, is_deleted=True).count()
        
        # Permanently delete all
        Relationship.objects.filter(family=family, is_deleted=True).delete()
        Person.objects.filter(family=family, is_deleted=True).delete()
        
        # Create audit log
        AuditLog.objects.create(
            family=family,
            user=request.user,
            action=AuditLog.Action.DELETE,
            object_type=AuditLog.ObjectType.FAMILY,
            object_id=family.id,
            object_repr=f"EMPTY TRASH: {person_count} persons, {rel_count} relationships",
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
        )
        
        messages.success(request, f"Trash emptied. {person_count} persons and {rel_count} relationships permanently deleted.")
        return redirect("families:trash_bin", family_id=family.id)
    
    return redirect("families:trash_bin", family_id=family.id)
