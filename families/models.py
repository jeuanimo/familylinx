"""
Families App - Models

This module defines the core data models for the FamilyLinx application's
family management functionality. It implements a role-based access control
system for family spaces.

Models:
    - FamilySpace: The main container for a family group
    - Membership: User-to-family relationship with role-based permissions
    - Invite: Email-based invitation system with secure tokens

Security Considerations (OWASP):
    - Uses Django's ORM for parameterized queries (prevents SQL injection)
    - Implements role-based access control (broken access control prevention)
    - Secure token generation using secrets module (cryptographic security)
    - ForeignKey with PROTECT prevents accidental data deletion
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
import secrets


class FamilySpace(models.Model):
    """
    Represents a family group/space that users can join and collaborate in.
    
    A FamilySpace is the primary organizational unit in FamilyLinx. Each space
    can have multiple members with different roles and permissions.
    
    Attributes:
        name (str): Display name of the family space (max 120 chars)
        description (str): Optional description of the family space
        created_by (User): The user who created this space (protected from deletion)
        created_at (datetime): Timestamp when the space was created
        root_person_1_id (int): Future use - first anchor for family tree
        root_person_2_id (int): Future use - second anchor for family tree
    
    Related Models:
        - Membership: Access via `memberships` related name
        - Invite: Access via `invites` related name
    
    Example:
        >>> space = FamilySpace.objects.create(
        ...     name="Smith Family",
        ...     description="Our family history",
        ...     created_by=user
        ... )
    """
    
    # Core fields
    name = models.CharField(
        max_length=120,
        help_text="Display name for the family space"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of the family space"
    )
    
    # Ownership tracking - PROTECT prevents deletion of user while families exist
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_families",
        help_text="User who created this family space"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when space was created"
    )

    # Future family tree anchor points
    # These will link to Person records once the tree phase is implemented
    root_person_1_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Future: ID of first root person in family tree"
    )
    root_person_2_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Future: ID of second root person in family tree"
    )

    def __str__(self):
        """Return the family space name for display."""
        return self.name

    class Meta:
        verbose_name = "Family Space"
        verbose_name_plural = "Family Spaces"
        ordering = ['-created_at']


class Membership(models.Model):
    """
    Defines the relationship between a User and a FamilySpace with role-based permissions.
    
    Implements role-based access control (RBAC) following the principle of least
    privilege. Each user can have only one membership per family space.
    
    Role Hierarchy (highest to lowest):
        - OWNER: Full control, can delete family space
        - ADMIN: Can manage members and invites
        - EDITOR: Can modify family tree data
        - MEMBER: Can view and add basic content
        - VIEWER: Read-only access
    
    Attributes:
        family (FamilySpace): The family space this membership belongs to
        user (User): The user who has this membership
        role (str): Permission level (see Role choices)
        joined_at (datetime): When the user joined the family space
    
    Security Notes:
        - unique_together constraint prevents duplicate memberships
        - CASCADE delete removes membership when user or family is deleted
        - Role checks should be performed in views before allowing actions
    
    Example:
        >>> membership = Membership.objects.create(
        ...     family=family_space,
        ...     user=user,
        ...     role=Membership.Role.MEMBER
        ... )
        >>> if membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        ...     # Allow admin actions
    """
    
    class Role(models.TextChoices):
        """
        Enumeration of available membership roles.
        
        Roles are ordered by permission level (highest first):
        - OWNER: Full administrative control
        - ADMIN: Can manage members and settings
        - EDITOR: Can modify family tree content
        - MEMBER: Standard access, can add content
        - VIEWER: Read-only access
        """
        OWNER = "OWNER", "Owner"
        ADMIN = "ADMIN", "Admin"
        EDITOR = "EDITOR", "Editor"
        MEMBER = "MEMBER", "Member"
        VIEWER = "VIEWER", "Viewer"

    # Relationship fields
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text="The family space this membership belongs to"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
        help_text="The user who has this membership"
    )
    
    # Permission and tracking fields
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER,
        help_text="Permission level for this membership"
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when user joined the family space"
    )
    
    # Link to Person record in the family tree
    linked_person = models.ForeignKey(
        'Person',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_membership",
        help_text="The Person record in the family tree that represents this user"
    )

    class Meta:
        # Ensures each user can only have one membership per family
        unique_together = ("family", "user")
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"
        ordering = ['joined_at']

    def __str__(self):
        """Return a descriptive string showing user, family, and role."""
        return f"{self.user} in {self.family} ({self.role})"


class Invite(models.Model):
    """
    Represents an email invitation to join a FamilySpace.
    
    Invitations use secure tokens for URL-based acceptance. Tokens are generated
    using Python's secrets module for cryptographic security.
    
    Lifecycle:
        1. Admin/Owner creates invite with email and role
        2. System generates secure token and sets expiration (14 days default)
        3. Email sent to recipient with acceptance link (future)
        4. Recipient clicks link, logs in, and accepts invite
        5. Membership created with specified role, invite marked as accepted
    
    Attributes:
        family (FamilySpace): Target family space for the invite
        email (str): Email address of the invitee
        token (str): Secure URL-safe token (auto-generated)
        role (str): Role to assign upon acceptance
        created_by (User): Admin/Owner who created the invite
        created_at (datetime): When invite was created
        expires_at (datetime): When invite expires (default: 14 days)
        accepted_at (datetime): When invite was accepted (null if pending)
    
    Security Notes:
        - Token is generated using secrets.token_urlsafe(32) - 256 bits of entropy
        - Token is unique and non-editable after creation
        - Expiration prevents stale invites from being accepted
        - is_valid property checks both acceptance status and expiration
    
    Example:
        >>> invite = Invite.objects.create(
        ...     family=family_space,
        ...     email="newmember@example.com",
        ...     role=Membership.Role.MEMBER,
        ...     created_by=admin_user
        ... )
        >>> # Token and expires_at are auto-generated on save
        >>> invite.is_valid  # True if not expired and not accepted
    """
    
    # Relationship fields
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="invites",
        help_text="Family space this invite is for"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_invites",
        help_text="User who created this invite"
    )
    
    # Invite details
    email = models.EmailField(
        help_text="Email address to send the invite to"
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Secure token for invite URL (auto-generated)"
    )
    role = models.CharField(
        max_length=10,
        choices=Membership.Role.choices,
        default=Membership.Role.MEMBER,
        help_text="Role to assign when invite is accepted"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the invite was created"
    )
    expires_at = models.DateTimeField(
        help_text="When the invite expires (default: 14 days from creation)"
    )
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the invite was accepted (null if pending)"
    )

    def save(self, *args, **kwargs):
        """
        Override save to auto-generate token and expiration date.
        
        Token Generation:
            Uses secrets.token_urlsafe(32) which generates a URL-safe
            base64-encoded token with 256 bits of randomness.
        
        Expiration:
            Default expiration is 14 days from creation if not specified.
        """
        # Generate secure token if not already set
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        
        # Set default expiration if not specified
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=14)
        
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """
        Check if the invite can still be accepted.
        
        Returns:
            bool: True if invite has not been accepted AND has not expired
        
        Note:
            This should be checked before creating a membership from an invite.
        """
        return self.accepted_at is None and timezone.now() < self.expires_at

    def __str__(self):
        """Return a descriptive string showing email and target family."""
        return f"Invite {self.email} to {self.family}"

    class Meta:
        verbose_name = "Invite"
        verbose_name_plural = "Invites"
        ordering = ['-created_at']


# =============================================================================
# Phase 2: Social Feed Models
# =============================================================================

class Post(models.Model):
    """
    Represents a post in a family space's social feed.
    
    Posts can contain text content and optionally an image. Only members
    of the family space can view and create posts.
    
    Attributes:
        family (FamilySpace): The family space this post belongs to
        author (User): The user who created this post
        content (str): The text content of the post
        image (ImageField): Optional image attachment
        created_at (datetime): When the post was created
        updated_at (datetime): When the post was last modified
        is_pinned (bool): Whether this post is pinned to top of feed
        is_hidden (bool): Moderation flag to hide inappropriate content
    
    Security Notes:
        - Posts are scoped to family space (privacy enforcement)
        - Only family members can view posts
        - Moderation via is_hidden flag for admins
    """
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="posts",
        help_text="The family space this post belongs to"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
        help_text="The user who created this post"
    )
    content = models.TextField(
        help_text="The text content of the post"
    )
    image = models.ImageField(
        upload_to="posts/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional image attachment"
    )
    video = models.FileField(
        upload_to="posts/videos/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional video attachment"
    )
    tagged_people = models.ManyToManyField(
        "Person",
        blank=True,
        related_name="tagged_posts",
        help_text="Family members tagged in this post"
    )
    liked_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="liked_family_posts",
        help_text="Members who liked this post"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the post was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When the post was last modified"
    )
    
    # Moderation fields
    is_pinned = models.BooleanField(
        default=False,
        help_text="Pin this post to the top of the feed"
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hide this post (moderation)"
    )
    
    def __str__(self):
        """Return truncated content preview."""
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.author.email}: {preview}"

    @property
    def like_count(self):
        """Return the number of likes on the post."""
        return self.liked_by.count()
    
    class Meta:
        verbose_name = "Post"
        verbose_name_plural = "Posts"
        ordering = ['-is_pinned', '-created_at']


class Comment(models.Model):
    """
    Represents a comment on a post in the social feed.
    
    Comments allow family members to reply to posts. Comments can be
    moderated by family admins.
    
    Attributes:
        post (Post): The post this comment belongs to
        author (User): The user who wrote this comment
        content (str): The comment text
        created_at (datetime): When the comment was created
        is_hidden (bool): Moderation flag to hide inappropriate content
    
    Security Notes:
        - Comments inherit privacy from parent post/family
        - Only family members can comment
        - Moderation via is_hidden flag
    """
    
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="The post this comment belongs to"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="The user who wrote this comment"
    )
    content = models.TextField(
        help_text="The comment text"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the comment was created"
    )
    
    # Moderation
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hide this comment (moderation)"
    )
    
    def __str__(self):
        """Return truncated comment preview."""
        preview = self.content[:30] + "..." if len(self.content) > 30 else self.content
        return f"{self.author.email}: {preview}"
    
    class Meta:
        verbose_name = "Comment"
        verbose_name_plural = "Comments"
        ordering = ['created_at']


class Event(models.Model):
    """
    Represents a family event (reunion, birthday, holiday gathering, etc.).
    
    Events are tied to a FamilySpace and allow members to RSVP.
    Supports recurring event types like birthdays.
    
    Attributes:
        family (FamilySpace): The family this event belongs to
        title (str): Event title
        description (str): Optional event description
        event_type (str): Category of event (birthday, reunion, holiday, other)
        start_datetime (datetime): When the event starts
        end_datetime (datetime): When the event ends (optional)
        location (str): Where the event takes place
        created_by (User): Who created this event
        created_at (datetime): When the event was created
    
    Security Notes:
        - Events only visible to family members
        - Only admins/owners can edit/delete events
    """
    
    class EventType(models.TextChoices):
        BIRTHDAY = 'BIRTHDAY', 'Birthday'
        REUNION = 'REUNION', 'Family Reunion'
        HOLIDAY = 'HOLIDAY', 'Holiday Gathering'
        ANNIVERSARY = 'ANNIVERSARY', 'Anniversary'
        FUNERAL = 'FUNERAL', 'Funeral'
        MEMORIAL = 'MEMORIAL', 'Memorial'
        OTHER = 'OTHER', 'Other'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="events",
        help_text="The family this event belongs to"
    )
    title = models.CharField(
        max_length=200,
        help_text="Event title"
    )
    description = models.TextField(
        blank=True,
        help_text="Event description and details"
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        default=EventType.OTHER,
        help_text="Type of event"
    )
    
    # Date/Time
    start_datetime = models.DateTimeField(
        help_text="When the event starts"
    )
    end_datetime = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the event ends (optional)"
    )
    
    # Location
    location = models.CharField(
        max_length=300,
        blank=True,
        help_text="Event location/address"
    )
    
    # Event image
    image = models.ImageField(
        upload_to="events/",
        blank=True,
        null=True,
        help_text="Event cover image or flyer"
    )
    notify_members = models.BooleanField(
        default=True,
        help_text="Notify family members when this event is created or updated"
    )
    send_reminders = models.BooleanField(
        default=True,
        help_text="Send reminder notifications before the event"
    )
    reminder_days_before = models.PositiveIntegerField(
        default=7,
        help_text="How many days before the event reminders should be sent"
    )
    
    # Creator info
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_events",
        help_text="User who created this event"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this event was created"
    )
    
    def __str__(self):
        return f"{self.title} ({self.start_datetime.strftime('%b %d, %Y')})"
    
    @property
    def is_past(self):
        """Check if the event has already occurred."""
        return self.start_datetime < timezone.now()
    
    @property
    def rsvp_counts(self):
        """Get counts of RSVPs by status."""
        from django.db.models import Count
        counts = self.rsvps.values('status').annotate(count=Count('id'))
        result = {'GOING': 0, 'MAYBE': 0, 'NOT_GOING': 0}
        for item in counts:
            result[item['status']] = item['count']
        return result
    
    class Meta:
        verbose_name = "Event"
        verbose_name_plural = "Events"
        ordering = ['start_datetime']


class RSVP(models.Model):
    """
    Tracks a user's response to a family event.
    
    Attributes:
        event (Event): The event being responded to
        user (User): The user responding
        status (str): Going, Maybe, or Not Going
        responded_at (datetime): When the response was recorded
    
    Constraints:
        - One RSVP per user per event (unique_together)
    """
    
    class Status(models.TextChoices):
        GOING = 'GOING', 'Going'
        MAYBE = 'MAYBE', 'Maybe'
        NOT_GOING = 'NOT_GOING', 'Not Going'
    
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="rsvps",
        help_text="The event being responded to"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rsvps",
        help_text="The user responding"
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        help_text="RSVP status"
    )
    responded_at = models.DateTimeField(
        auto_now=True,
        help_text="When the RSVP was submitted/updated"
    )
    
    def __str__(self):
        return f"{self.user.email} - {self.status} for {self.event.title}"
    
    class Meta:
        verbose_name = "RSVP"
        verbose_name_plural = "RSVPs"
        unique_together = ['event', 'user']


class EventReminderLog(models.Model):
    """
    Tracks reminder notifications already sent for an event occurrence.
    """

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="reminder_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_reminder_logs",
    )
    reminder_for_date = models.DateField(
        help_text="The event date this reminder was sent for"
    )
    notified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("event", "user", "reminder_for_date")]
        ordering = ["-notified_at"]

    def __str__(self):
        return f"Reminder for {self.user.email} about {self.event.title}"


# =============================================================================
# Phase 4: Family Tree Models
# =============================================================================

class Person(models.Model):
    """
    Represents an individual in the family tree.
    
    A Person can be linked to a user account (for living family members)
    or exist as a historical record (for ancestors). Each person belongs
    to a FamilySpace and can have relationships with other persons.
    
    Attributes:
        family (FamilySpace): The family this person belongs to
        first_name (str): Person's first/given name
        last_name (str): Person's family/surname
        maiden_name (str): Birth surname if different (optional)
        gender (str): Male, Female, or Other
        birth_date (date): Date of birth (optional for privacy)
        death_date (date): Date of death if deceased (optional)
        birth_place (str): Place of birth
        death_place (str): Place of death
        bio (str): Biography/notes about this person
        photo (ImageField): Profile photo
        linked_user (User): Optional link to a FamilyLinx user account
        created_by (User): Who added this person
        created_at (datetime): When this record was created
    
    Security Notes:
        - Persons are scoped to FamilySpace (privacy)
        - Only family members can view/edit
        - Sensitive dates can be hidden via privacy settings
    """
    
    class Gender(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'
        OTHER = 'O', 'Other'
        UNKNOWN = 'U', 'Unknown'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="persons",
        help_text="The family this person belongs to"
    )
    
    # Name fields
    first_name = models.CharField(
        max_length=100,
        help_text="First/given name"
    )
    last_name = models.CharField(
        max_length=100,
        help_text="Family/surname"
    )
    maiden_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Birth surname if different (e.g., before marriage)"
    )
    
    # Demographics
    gender = models.CharField(
        max_length=1,
        choices=Gender.choices,
        default=Gender.UNKNOWN,
        help_text="Gender"
    )
    
    # Vital dates
    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of birth"
    )
    birth_date_qualifier = models.CharField(
        max_length=10,
        blank=True,
        help_text="Date qualifier: ABT (about), BEF (before), AFT (after), EST (estimated)"
    )
    death_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of death (leave blank if living)"
    )
    death_date_qualifier = models.CharField(
        max_length=10,
        blank=True,
        help_text="Date qualifier: ABT (about), BEF (before), AFT (after), EST (estimated)"
    )
    
    # Privacy flag for living persons
    is_private = models.BooleanField(
        default=False,
        help_text="Mark as private to hide details from non-family viewers"
    )
    
    # Places
    birth_place = models.CharField(
        max_length=200,
        blank=True,
        help_text="Place of birth"
    )
    death_place = models.CharField(
        max_length=200,
        blank=True,
        help_text="Place of death"
    )
    
    # Bio and photo
    bio = models.TextField(
        blank=True,
        help_text="Biography, notes, or stories about this person"
    )
    photo = models.ImageField(
        upload_to="persons/",
        blank=True,
        null=True,
        help_text="Profile photo"
    )
    
    # Link to user account (optional)
    linked_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_profile",
        help_text="Link to a FamilyLinx user account (optional)"
    )
    
    # Tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="persons_created",
        help_text="User who added this person"
    )
    source_import = models.ForeignKey(
        'GedcomImport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imported_persons",
        help_text="GEDCOM import that created this person (if any)"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this record was last updated"
    )
    
    # Soft delete fields
    is_deleted = models.BooleanField(
        default=False,
        help_text="Whether this person has been soft-deleted"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this person was deleted"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="persons_deleted",
        help_text="User who deleted this person"
    )
    
    def soft_delete(self, user):
        """Soft delete this person instead of removing from database."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save()
        # Also soft delete related relationships
        from families.models import Relationship
        Relationship.objects.filter(
            models.Q(person1=self) | models.Q(person2=self)
        ).update(is_deleted=True, deleted_at=timezone.now(), deleted_by=user)
    
    def restore(self):
        """Restore a soft-deleted person."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save()
        # Also restore related relationships
        from families.models import Relationship
        Relationship.objects.filter(
            models.Q(person1=self) | models.Q(person2=self)
        ).update(is_deleted=False, deleted_at=None, deleted_by=None)
    
    def __str__(self):
        name = f"{self.first_name} {self.last_name}"
        if self.maiden_name:
            name += f" (née {self.maiden_name})"
        return name
    
    @property
    def full_name(self):
        """Return the full name."""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_living(self):
        """Check if person is still living (no death date)."""
        return self.death_date is None
    
    @property
    def display_photo_url(self):
        """
        Get the best available photo URL for this person.
        Priority: 1. Person's own photo, 2. Linked user's profile picture
        Returns URL string or None.
        """
        # First check person's own photo
        if self.photo:
            return self.photo.url
        
        # Then check linked user's profile picture
        if self.linked_user:
            try:
                profile = self.linked_user.profile
                if profile and profile.profile_picture:
                    return profile.profile_picture.url
            except Exception:
                pass
        
        return None

    @property
    def parents(self):
        """Get parents of this person."""
        parent_rels = self.child_relationships.filter(
            relationship_type=Relationship.Type.PARENT_CHILD
        ).select_related('person1')
        return [rel.person1 for rel in parent_rels]
    
    @staticmethod
    def _get_generation_label(gen_num):
        """Get the label for a generation number (2=Grandparents, 3=Great-GP, etc.)."""
        if gen_num == 2:
            return "Grandparents"
        if gen_num == 3:
            return "Great-Grandparents"
        prefix = "Great-" * (gen_num - 2)
        return f"{prefix}Grandparents"

    @property
    def ancestors(self):
        """
        Get all direct ancestors organized by generation.
        Returns a list of dicts: [{'label': 'Grandparents', 'persons': [...]}]
        """
        result = []
        current_gen = self.parents
        gen_num = 2  # Start at grandparents (parents are handled separately)
        
        while current_gen and gen_num <= 20:
            next_gen = []
            for person in current_gen:
                next_gen.extend(p for p in person.parents if p not in next_gen)
            
            if next_gen:
                result.append({
                    'label': self._get_generation_label(gen_num),
                    'persons': next_gen,
                })
            
            current_gen = next_gen
            gen_num += 1
        
        return result
    
    @property
    def children(self):
        """Get children of this person."""
        child_rels = self.parent_relationships.filter(
            relationship_type=Relationship.Type.PARENT_CHILD
        ).select_related('person2')
        return [rel.person2 for rel in child_rels]
    
    @property
    def spouses(self):
        """Get spouses of this person."""
        spouse_rels1 = self.parent_relationships.filter(
            relationship_type=Relationship.Type.SPOUSE
        ).select_related('person2')
        spouse_rels2 = self.child_relationships.filter(
            relationship_type=Relationship.Type.SPOUSE
        ).select_related('person1')
        return [rel.person2 for rel in spouse_rels1] + [rel.person1 for rel in spouse_rels2]
    
    @property
    def siblings(self):
        """Get siblings of this person."""
        # Find all parents, then find all their children except self
        my_parents = self.parents
        siblings = set()
        for parent in my_parents:
            for child in parent.children:
                if child.id != self.id:
                    siblings.add(child)
        return list(siblings)
    
    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "People"
        ordering = ['last_name', 'first_name']


class Relationship(models.Model):
    """
    Represents a relationship between two persons in the family tree.
    
    Relationships are directional:
    - PARENT_CHILD: person1 is parent, person2 is child
    - SPOUSE: person1 and person2 are spouses (symmetric)
    
    Attributes:
        family (FamilySpace): The family this relationship belongs to
        person1 (Person): First person in relationship
        person2 (Person): Second person in relationship
        relationship_type (str): Type of relationship
        start_date (date): When relationship started (e.g., marriage date)
        end_date (date): When relationship ended (e.g., divorce date)
        notes (str): Additional notes about the relationship
    
    Constraints:
        - Both persons must be in the same family
        - No duplicate relationships allowed
    """
    
    class Type(models.TextChoices):
        # Direct relationships
        PARENT_CHILD = 'PARENT_CHILD', 'Parent-Child'
        SPOUSE = 'SPOUSE', 'Spouse'
        
        # Grandparent relationships (person1 is ancestor, person2 is descendant)
        GRANDPARENT = 'GRANDPARENT', 'Grandparent-Grandchild'
        GREAT_GRANDPARENT = 'GREAT_GRANDPARENT', 'Great-Grandparent'
        GREAT_GRANDPARENT_2X = 'GREAT_GRANDPARENT_2X', '2nd Great-Grandparent'
        GREAT_GRANDPARENT_3X = 'GREAT_GRANDPARENT_3X', '3rd Great-Grandparent'
        GREAT_GRANDPARENT_4X = 'GREAT_GRANDPARENT_4X', '4th Great-Grandparent'
        GREAT_GRANDPARENT_5X = 'GREAT_GRANDPARENT_5X', '5th Great-Grandparent'
        GREAT_GRANDPARENT_6X = 'GREAT_GRANDPARENT_6X', '6th Great-Grandparent'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="relationships",
        help_text="The family this relationship belongs to"
    )
    person1 = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="parent_relationships",
        help_text="First person (parent in parent-child, either in spouse)"
    )
    person2 = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="child_relationships",
        help_text="Second person (child in parent-child, either in spouse)"
    )
    relationship_type = models.CharField(
        max_length=25,
        choices=Type.choices,
        help_text="Type of relationship"
    )
    
    # Optional dates (e.g., marriage/divorce dates for spouse relationships)
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date (e.g., marriage date)"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date (e.g., divorce date)"
    )
    
    notes = models.TextField(
        blank=True,
        help_text="Additional notes about this relationship"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this relationship was recorded"
    )
    
    # Soft delete fields
    is_deleted = models.BooleanField(
        default=False,
        help_text="Whether this relationship has been soft-deleted"
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this relationship was deleted"
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="relationships_deleted",
        help_text="User who deleted this relationship"
    )
    
    def soft_delete(self, user):
        """Soft delete this relationship."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save()
    
    def restore(self):
        """Restore a soft-deleted relationship."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save()
    
    def __str__(self):
        if self.relationship_type == self.Type.PARENT_CHILD:
            return f"{self.person1.full_name} → parent of → {self.person2.full_name}"
        return f"{self.person1.full_name} ↔ spouse ↔ {self.person2.full_name}"
    
    def clean(self):
        """Validate that both persons are in the same family."""
        from django.core.exceptions import ValidationError
        if self.person1.family_id != self.person2.family_id:
            raise ValidationError("Both persons must be in the same family.")
        if self.person1.family_id != self.family_id:
            raise ValidationError("Relationship must be in the same family as the persons.")
    
    class Meta:
        verbose_name = "Relationship"
        verbose_name_plural = "Relationships"
        unique_together = ['person1', 'person2', 'relationship_type']


# =============================================================================
# Pending Person Changes (Approval Workflow)
# =============================================================================

class PendingPersonChange(models.Model):
    """
    Person changes submitted by non-admins that require approval.
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="pending_person_changes"
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_changes"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="person_change_requests"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_change_reviews"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    def __str__(self):
        target = self.person.full_name if self.person else "(new person)"
        return f"{self.action} {target} [{self.status}]"


# =============================================================================
# Phase 5: Photo Albums
# =============================================================================

class Album(models.Model):
    """
    A photo album belonging to a family space.
    
    Albums organize photos into collections, such as:
    - Family reunions
    - Holidays
    - Weddings
    - Historical photos
    
    Attributes:
        family (FamilySpace): The family this album belongs to
        title (str): Album name
        description (str): Optional description
        cover_photo (Photo): Optional cover image for the album
        created_by (User): Who created the album
        created_at (datetime): When created
        updated_at (datetime): When last modified
    """
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="albums",
        help_text="The family space this album belongs to"
    )
    title = models.CharField(
        max_length=200,
        help_text="Album title"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional description of this album"
    )
    event = models.ForeignKey(
        'Event',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="albums",
        help_text="Event this album is associated with (optional)"
    )
    primary_person = models.ForeignKey(
        'Person',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="person_albums",
        help_text="Highlight person this album is centered on (optional)"
    )
    class MediaFocus(models.TextChoices):
        MIXED = "MIXED", "Mixed Media"
        PHOTOS = "PHOTOS", "Photos"
        VIDEOS = "VIDEOS", "Videos"
        DOCUMENTS = "DOCUMENTS", "Documents"

    cover_photo = models.ForeignKey(
        'Photo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text="Cover photo for this album"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_albums",
        help_text="User who created this album"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this album was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this album was last modified"
    )
    media_focus = models.CharField(
        max_length=15,
        choices=MediaFocus.choices,
        default=MediaFocus.MIXED,
        help_text="Primary media type for this album"
    )
    
    def __str__(self):
        return f"{self.title} ({self.family.name})"
    
    @property
    def photo_count(self):
        """Return the number of photos in this album."""
        return self.photos.count()

    @property
    def cover_media(self):
        """Return the best media item to use as cover (photo preferred)."""
        candidate = None
        if self.cover_photo and self.cover_photo.media_type == Photo.MediaType.PHOTO:
            if self.cover_photo.image or self.cover_photo.file:
                candidate = self.cover_photo
        if not candidate:
            candidate = (
                self.photos.filter(media_type=Photo.MediaType.PHOTO)
                .exclude(image="")
                .first()
            )
        if not candidate:
            candidate = self.photos.filter(media_type=Photo.MediaType.PHOTO).first()
        return candidate
    
    class Meta:
        verbose_name = "Album"
        verbose_name_plural = "Albums"
        ordering = ['-created_at']


class Photo(models.Model):
    """
    A photo in an album.
    
    Media items can be photos, videos, or documents and support tagging people.
    
    Attributes:
        album (Album): The album this photo belongs to
        media_type (str): PHOTO, VIDEO, or DOCUMENT
        image (ImageField): The uploaded image file (for photos)
        file (FileField): Generic file field for video/document uploads
        caption (str): Optional caption/description
        taken_date (date): When the photo was taken
        taken_location (str): Where the photo was taken
        tagged_people (Person[]): People appearing in this photo
        uploaded_by (User): Who uploaded this photo
        uploaded_at (datetime): When uploaded
    """

    class MediaType(models.TextChoices):
        PHOTO = "PHOTO", "Photo"
        VIDEO = "VIDEO", "Video"
        DOCUMENT = "DOCUMENT", "Document"
    
    album = models.ForeignKey(
        Album,
        on_delete=models.CASCADE,
        related_name="photos",
        help_text="The album this photo belongs to"
    )
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        default=MediaType.PHOTO,
        help_text="Type of media"
    )
    image = models.ImageField(
        upload_to="photos/%Y/%m/",
        blank=True,
        null=True,
        help_text="The photo image file"
    )
    file = models.FileField(
        upload_to="media/files/%Y/%m/",
        blank=True,
        null=True,
        help_text="Uploaded video or document file"
    )
    caption = models.CharField(
        max_length=500,
        blank=True,
        help_text="Caption or description for this photo"
    )
    taken_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the photo was taken"
    )
    taken_location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Location where the photo was taken"
    )
    tagged_people = models.ManyToManyField(
        Person,
        blank=True,
        related_name="tagged_photos",
        help_text="People appearing in this photo"
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_items",
        help_text="Event this media belongs to (optional)"
    )
    primary_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_media_items",
        help_text="Person this media is centered on (optional)"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_photos",
        help_text="User who uploaded this photo"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this photo was uploaded"
    )
    
    def __str__(self):
        label = self.get_media_type_display()
        if self.caption:
            return f"{label}: {self.caption[:50]}..."
        return f"{label} {self.id} in {self.album.title}"
    
    class Meta:
        verbose_name = "Photo"
        verbose_name_plural = "Photos"
        ordering = ['-taken_date', '-uploaded_at']


# =============================================================================
# Living Museum - Stories, Memories & Tributes
# =============================================================================

class MemoryStory(models.Model):
    """
    A story, memory, or tribute about a person in the family tree.
    
    The Living Museum allows family members to share memories, anecdotes,
    and stories about their relatives - creating a rich narrative history.
    
    Attributes:
        person (Person): The person this memory is about
        title (str): Title of the story/memory
        content (str): The story content (rich text)
        story_type (str): Type of memory (story, tribute, biography, etc.)
        author (User): Who wrote this memory
        date_of_memory (date): When this memory took place (optional)
        is_featured (bool): Featured on person's profile
        is_public (bool): Visible to shared/guest viewers
    """
    
    class StoryType(models.TextChoices):
        MEMORY = 'MEMORY', 'Memory'
        STORY = 'STORY', 'Story'
        TRIBUTE = 'TRIBUTE', 'Tribute'
        BIOGRAPHY = 'BIOGRAPHY', 'Biography'
        MILESTONE = 'MILESTONE', 'Life Milestone'
        TRADITION = 'TRADITION', 'Family Tradition'
        RECIPE = 'RECIPE', 'Family Recipe'
        LESSON = 'LESSON', 'Life Lesson'
    
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="memories",
        help_text="The person this memory is about"
    )
    title = models.CharField(
        max_length=200,
        help_text="Title of the story or memory"
    )
    content = models.TextField(
        help_text="The story content"
    )
    story_type = models.CharField(
        max_length=20,
        choices=StoryType.choices,
        default=StoryType.MEMORY,
        help_text="Type of memory"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="authored_memories",
        help_text="Who wrote this memory"
    )
    date_of_memory = models.DateField(
        null=True,
        blank=True,
        help_text="When this memory took place"
    )
    location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Where this memory took place"
    )
    is_featured = models.BooleanField(
        default=False,
        help_text="Feature this memory on the person's profile"
    )
    is_public = models.BooleanField(
        default=False,
        help_text="Make visible to shared/guest viewers"
    )
    
    # Engagement
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this memory has been viewed"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this memory was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this memory was last modified"
    )
    
    def __str__(self):
        return f"{self.title} - {self.person.full_name}"
    
    @property
    def family(self):
        """Get the family space this memory belongs to."""
        return self.person.family
    
    class Meta:
        verbose_name = "Memory/Story"
        verbose_name_plural = "Memories & Stories"
        ordering = ['-is_featured', '-created_at']


class MemoryMedia(models.Model):
    """
    Media attachment for a memory (photos, videos, audio).
    
    Allows rich multimedia storytelling with photos, videos, and audio
    recordings attached to memory stories.
    
    Attributes:
        memory (MemoryStory): The memory this media belongs to
        media_type (str): Type of media (photo, video, audio)
        file (FileField): The media file
        caption (str): Optional caption
        order (int): Display order
    """
    
    class MediaType(models.TextChoices):
        PHOTO = 'PHOTO', 'Photo'
        VIDEO = 'VIDEO', 'Video'
        AUDIO = 'AUDIO', 'Audio Recording'
        DOCUMENT = 'DOCUMENT', 'Document'
    
    memory = models.ForeignKey(
        MemoryStory,
        on_delete=models.CASCADE,
        related_name="media",
        help_text="The memory this media belongs to"
    )
    media_type = models.CharField(
        max_length=20,
        choices=MediaType.choices,
        default=MediaType.PHOTO,
        help_text="Type of media"
    )
    file = models.FileField(
        upload_to="museum/%Y/%m/",
        help_text="The media file"
    )
    thumbnail = models.ImageField(
        upload_to="museum/thumbs/%Y/%m/",
        blank=True,
        null=True,
        help_text="Thumbnail for videos"
    )
    caption = models.CharField(
        max_length=500,
        blank=True,
        help_text="Caption for this media"
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_memory_media",
        help_text="Who uploaded this media"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this media was uploaded"
    )
    
    def __str__(self):
        return f"{self.media_type}: {self.caption[:30] if self.caption else 'No caption'}"
    
    class Meta:
        verbose_name = "Memory Media"
        verbose_name_plural = "Memory Media"
        ordering = ['order', 'uploaded_at']


class MemoryComment(models.Model):
    """
    Comments on memory stories from family members.
    
    Allows other family members to add their own recollections
    or reactions to shared memories.
    """
    
    memory = models.ForeignKey(
        MemoryStory,
        on_delete=models.CASCADE,
        related_name="comments",
        help_text="The memory being commented on"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memory_comments",
        help_text="Who wrote this comment"
    )
    content = models.TextField(
        max_length=1000,
        help_text="Comment text"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this comment was posted"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this comment was last edited"
    )
    
    def __str__(self):
        return f"Comment by {self.author.email} on {self.memory.title}"
    
    class Meta:
        verbose_name = "Memory Comment"
        verbose_name_plural = "Memory Comments"
        ordering = ['created_at']


class MemoryReaction(models.Model):
    """
    Reactions (like, love, etc.) on memory stories.
    """
    
    class ReactionType(models.TextChoices):
        LIKE = 'LIKE', '👍 Like'
        LOVE = 'LOVE', '❤️ Love'
        LAUGH = 'LAUGH', '😂 Laugh'
        CRY = 'CRY', '😢 Touching'
        WOW = 'WOW', '😮 Wow'
    
    memory = models.ForeignKey(
        MemoryStory,
        on_delete=models.CASCADE,
        related_name="reactions",
        help_text="The memory being reacted to"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memory_reactions",
        help_text="Who reacted"
    )
    reaction_type = models.CharField(
        max_length=10,
        choices=ReactionType.choices,
        default=ReactionType.LIKE,
        help_text="Type of reaction"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When reaction was added"
    )
    
    class Meta:
        verbose_name = "Memory Reaction"
        verbose_name_plural = "Memory Reactions"
        unique_together = [('memory', 'user')]


class LifeStory(models.Model):
    """Structured life story for a person with optional time-capsule release."""
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="life_stories",
        help_text="Person this life story belongs to"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_life_stories",
        help_text="User who created this life story"
    )
    title = models.CharField(max_length=200, default="Life Story")
    summary = models.TextField(blank=True, help_text="Optional overview paragraph")
    release_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Future release date (time capsule unlock)"
    )
    is_published = models.BooleanField(default=True, help_text="Show to family now")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def family(self):
        return self.person.family

    @property
    def is_unlocked(self):
        from django.utils import timezone
        return self.release_at is None or timezone.now() >= self.release_at

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Life Story"
        verbose_name_plural = "Life Stories"

    def __str__(self):
        return f"{self.title} for {self.person.full_name}"


class LifeStorySection(models.Model):
    """Sections within a life story (childhood, career, etc.)."""
    life_story = models.ForeignKey(
        LifeStory,
        on_delete=models.CASCADE,
        related_name="sections",
        help_text="Parent life story"
    )
    heading = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    audio = models.FileField(
        upload_to="lifestories/audio/%Y/%m/",
        null=True,
        blank=True,
        help_text="Optional audio recording"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"{self.heading} ({self.life_story.person.full_name})"


class TimeCapsule(models.Model):
    """Time capsule message scheduled for future release."""
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="time_capsules",
        help_text="Family this capsule belongs to"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_time_capsules",
        help_text="User who created this capsule"
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    open_at = models.DateTimeField(help_text="When this capsule unlocks")
    is_opened = models.BooleanField(default=False)
    attachment = models.FileField(
        upload_to="timecapsules/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional attachment (letter, video, zip)"
    )
    audio = models.FileField(
        upload_to="timecapsules/audio/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional audio recording"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["open_at"]

    def __str__(self):
        return f"{self.title} ({self.family.name})"

    @property
    def is_unlocked(self):
        from django.utils import timezone
        return self.is_opened or timezone.now() >= self.open_at


class FamilyMilestone(models.Model):
    """
    Custom family milestones (e.g., achievements, reunions, stories) with optional photo.
    """
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="milestones",
        help_text="Family this milestone belongs to"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()
    image = models.ImageField(
        upload_to="milestones/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional milestone photo"
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="milestones",
        help_text="Linked person (optional)"
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="milestones",
        help_text="Linked event (optional)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_milestones",
        help_text="User who added this milestone"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        verbose_name = "Family Milestone"
        verbose_name_plural = "Family Milestones"

    def __str__(self):
        return f"{self.title} ({self.date})"


class FamilyKudos(models.Model):
    """Exciting family announcements, wins, and celebrations."""
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="kudos_entries",
        help_text="Family this kudos entry belongs to"
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="kudos/%Y/%m/",
        blank=True,
        null=True,
        help_text="Optional image for the announcement"
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kudos_entries",
        help_text="Linked person (optional)"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_kudos_entries",
        help_text="User who added this kudos entry"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Family Kudos"
        verbose_name_plural = "Family Kudos"

    def __str__(self):
        return f"{self.title} ({self.family.name})"


class MuseumShare(models.Model):
    """
    Share the Living Museum or specific memories with others.
    
    Allows family members to share memories with:
    - Specific users (by email)
    - Anyone with a link (public share link)
    
    Attributes:
        share_type (str): What is being shared (memory, person, museum)
        memory (MemoryStory): Specific memory (if share_type is MEMORY)
        person (Person): Person's memories (if share_type is PERSON)
        family (FamilySpace): Entire museum (if share_type is MUSEUM)
        shared_by (User): Who created the share
        shared_with_email (str): Email of recipient (optional)
        shared_with_user (User): User recipient (if registered)
        share_token (str): Unique token for link sharing
        is_public_link (bool): Whether anyone with link can view
        expires_at (datetime): When share expires (optional)
    """
    
    class ShareType(models.TextChoices):
        MEMORY = 'MEMORY', 'Single Memory'
        PERSON = 'PERSON', "Person's Memories"
        MUSEUM = 'MUSEUM', 'Entire Museum'
    
    share_type = models.CharField(
        max_length=20,
        choices=ShareType.choices,
        default=ShareType.MEMORY,
        help_text="What is being shared"
    )
    
    # What is shared (one of these will be set based on share_type)
    memory = models.ForeignKey(
        MemoryStory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="shares",
        help_text="Specific memory being shared"
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="museum_shares",
        help_text="Person whose memories are being shared"
    )
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="museum_shares",
        help_text="Family whose entire museum is being shared"
    )
    
    # Who is sharing
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="museum_shares_created",
        help_text="User who created this share"
    )
    
    # Who is receiving (optional - can be public link)
    shared_with_email = models.EmailField(
        blank=True,
        help_text="Email of the recipient"
    )
    shared_with_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="museum_shares_received",
        help_text="User who received the share (if registered)"
    )
    
    # Share link token
    share_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text="Unique token for share link"
    )
    is_public_link = models.BooleanField(
        default=False,
        help_text="Anyone with the link can view"
    )
    
    # Optional message
    message = models.TextField(
        blank=True,
        max_length=500,
        help_text="Optional personal message"
    )
    
    # Expiration and tracking
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When share expires (null = never)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this share is currently active"
    )
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this share has been viewed"
    )
    last_viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the share was last viewed"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When share was created"
    )
    
    def save(self, *args, **kwargs):
        """Generate share token if not set."""
        import secrets
        if not self.share_token:
            self.share_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Check if share is still valid."""
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True
    
    def record_view(self):
        """Record a view of this share."""
        from django.utils import timezone
        self.view_count += 1
        self.last_viewed_at = timezone.now()
        self.save(update_fields=['view_count', 'last_viewed_at'])
    
    def can_access(self, user=None):
        """Check if user/visitor can access this share."""
        if not self.is_valid():
            return False
        
        # Public links are accessible to anyone
        if self.is_public_link:
            return True
        
        # If shared with specific user
        if user and self.shared_with_user == user:
            return True
        
        # If shared by email and user has that email
        if user and self.shared_with_email and user.email.lower() == self.shared_with_email.lower():
            return True
        
        return False
    
    def get_share_url(self):
        """Get the shareable URL for this share."""
        return f"/museum/shared/{self.share_token}/"
    
    def __str__(self):
        target = ""
        if self.share_type == self.ShareType.MEMORY and self.memory:
            target = self.memory.title
        elif self.share_type == self.ShareType.PERSON and self.person:
            target = f"{self.person.full_name}'s memories"
        elif self.share_type == self.ShareType.MUSEUM and self.family:
            target = f"{self.family.name} museum"
        
        recipient = self.shared_with_email or "Public Link"
        return f"Share: {target} → {recipient}"
    
    class Meta:
        verbose_name = "Museum Share"
        verbose_name_plural = "Museum Shares"
        ordering = ['-created_at']


# =============================================================================
# Phase 6: Notifications & Messaging
# =============================================================================

class Notification(models.Model):
    """
    In-app notification for user activity alerts.
    
    Notifications are triggered by various events (new posts, comments, events,
    invites, etc.) and displayed in the notification bell/dropdown.
    
    Attributes:
        recipient (User): User who receives this notification
        family (FamilySpace): The family space context (optional)
        notification_type (str): Type of notification for icon/styling
        title (str): Short notification title
        message (str): Notification content/body
        link (str): Optional URL to navigate to when clicked
        is_read (bool): Whether user has seen this notification
        created_at (datetime): When notification was created
    
    Security:
        - Only recipient can view their notifications
        - Family context ensures proper access control
    """
    
    class NotificationType(models.TextChoices):
        POST = 'POST', 'New Post'
        COMMENT = 'COMMENT', 'New Comment'
        EVENT = 'EVENT', 'Event Update'
        INVITE = 'INVITE', 'Invitation'
        RSVP = 'RSVP', 'RSVP Update'
        PHOTO = 'PHOTO', 'New Photo'
        PERSON = 'PERSON', 'Family Tree Update'
        CHAT = 'CHAT', 'New Message'
        SYSTEM = 'SYSTEM', 'System Alert'
    
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="User who receives this notification"
    )
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Family space context for this notification"
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
        help_text="Type of notification"
    )
    title = models.CharField(
        max_length=200,
        help_text="Short notification title"
    )
    message = models.TextField(
        blank=True,
        help_text="Notification content/body"
    )
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text="URL to navigate to when notification is clicked"
    )
    is_read = models.BooleanField(
        default=False,
        help_text="Whether user has seen this notification"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When notification was created"
    )
    
    def __str__(self):
        return f"{self.notification_type}: {self.title} → {self.recipient.email}"
    
    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]


class ChatMessage(models.Model):
    """
    Family group chat message.
    
    Each FamilySpace has a built-in group chat. Messages are visible to all
    family members and ordered by creation time.
    
    Attributes:
        family (FamilySpace): The family space this message belongs to
        author (User): User who sent the message
        content (str): Message text content
        created_at (datetime): When message was sent
        is_deleted (bool): Soft delete flag for moderation
    
    Security:
        - Only family members can view messages
        - Only author or admin can delete messages
        - Messages are sanitized on display
    """
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="chat_messages",
        help_text="Family space this message belongs to"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="chat_messages",
        help_text="User who sent this message"
    )
    content = models.TextField(
        max_length=2000,
        help_text="Message text content"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When message was sent"
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete flag for moderation"
    )
    
    def __str__(self):
        author_name = self.author.email if self.author else "Deleted User"
        return f"{author_name}: {self.content[:50]}..."
    
    class Meta:
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['family', 'created_at']),
        ]


class ChatConversation(models.Model):
    """
    Unified conversation model for direct, branch, event, and family chats.
    """

    class ConversationType(models.TextChoices):
        FAMILY = "FAMILY", "Family Chat"
        DIRECT = "DIRECT", "Direct Message"
        BRANCH = "BRANCH", "Family Branch"
        EVENT = "EVENT", "Event Chat"

    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="chat_conversations",
        help_text="Family space this conversation belongs to",
    )
    conversation_type = models.CharField(
        max_length=20,
        choices=ConversationType.choices,
        default=ConversationType.FAMILY,
        help_text="What kind of conversation this is",
    )
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional custom conversation title",
    )
    branch_root = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="branch_conversations",
        help_text="Root person for a family-branch conversation",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat_conversations",
        help_text="Event this conversation is attached to",
    )
    direct_key = models.CharField(
        max_length=120,
        null=True,
        blank=True,
        unique=True,
        help_text="Stable unique key for direct conversations",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_chat_conversations",
        help_text="User who created the conversation",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or f"{self.get_conversation_type_display()} ({self.family.name})"

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        indexes = [
            models.Index(fields=["family", "conversation_type"]),
            models.Index(fields=["family", "-updated_at"]),
        ]


class ChatConversationParticipant(models.Model):
    """
    Membership of a user inside a chat conversation.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="family_chat_participations",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("conversation", "user")]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user.email} in {self.conversation_id}"


class ChatConversationMessage(models.Model):
    """
    A message sent within a unified chat conversation.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name="messages",
        help_text="Conversation this message belongs to",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="family_conversation_messages",
        help_text="User who sent this message",
    )
    content = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        author_name = self.author.email if self.author else "Deleted User"
        return f"{author_name}: {self.content[:60]}"


class ChatMessageReadReceipt(models.Model):
    """
    Per-message read receipt for conversation participants.
    """

    message = models.ForeignKey(
        ChatConversationMessage,
        on_delete=models.CASCADE,
        related_name="read_receipts",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chat_read_receipts",
    )
    read_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("message", "user")]
        ordering = ["-read_at"]

    def __str__(self):
        return f"{self.user.email} read {self.message_id}"


def create_notification(recipient, notification_type, title, message="", link="", family=None):
    """
    Helper function to create a notification.
    
    Usage:
        create_notification(
            recipient=user,
            notification_type=Notification.NotificationType.POST,
            title="New post in Smith Family",
            message="John posted: Hello everyone!",
            link="/families/1/posts/5/",
            family=family_space
        )
    """
    return Notification.objects.create(
        recipient=recipient,
        family=family,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link
    )


# =============================================================================
# Phase 7: GEDCOM Import & Duplicate Detection
# =============================================================================

class GedcomImport(models.Model):
    """
    Tracks GEDCOM file import jobs and their status.
    
    Supports both synchronous and background processing.
    Stores import statistics and error logs for reporting.
    
    Attributes:
        family (FamilySpace): Target family space for import
        uploaded_by (User): User who initiated the import
        file_name (str): Original filename
        file_size (int): File size in bytes
        status (str): Current processing status
        started_at (datetime): When processing began
        completed_at (datetime): When processing finished
        persons_created (int): Count of new persons
        persons_updated (int): Count of updated persons
        relationships_created (int): Count of new relationships
        duplicates_found (int): Count of potential duplicates
        errors (text): JSON array of error messages
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="gedcom_imports",
        help_text="Family space to import into"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="gedcom_imports",
        help_text="User who uploaded the file"
    )
    file_name = models.CharField(
        max_length=255,
        help_text="Original filename"
    )
    file_size = models.PositiveIntegerField(
        default=0,
        help_text="File size in bytes"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current processing status"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When import was initiated"
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing started"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When processing completed"
    )
    
    # Statistics
    persons_created = models.PositiveIntegerField(default=0)
    persons_updated = models.PositiveIntegerField(default=0)
    relationships_created = models.PositiveIntegerField(default=0)
    duplicates_found = models.PositiveIntegerField(default=0)
    
    # Error log (JSON array)
    errors = models.TextField(
        blank=True,
        default="[]",
        help_text="JSON array of error messages"
    )
    
    def __str__(self):
        return f"GEDCOM Import: {self.file_name} ({self.status})"
    
    class Meta:
        verbose_name = "GEDCOM Import"
        verbose_name_plural = "GEDCOM Imports"
        ordering = ['-created_at']


class PotentialDuplicate(models.Model):
    """
    Tracks potential duplicate persons found during GEDCOM import.
    
    When importing, if a person closely matches an existing person,
    a PotentialDuplicate record is created for manual review.
    
    Attributes:
        gedcom_import (GedcomImport): The import job that found this
        existing_person (Person): The existing person in database
        imported_person (Person): The newly imported person
        confidence_score (float): Match confidence 0-100
        match_reasons (text): JSON explaining why matched
        status (str): Review status
        reviewed_by (User): Who reviewed the duplicate
        reviewed_at (datetime): When it was reviewed
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        MERGED = 'MERGED', 'Merged'
        KEPT_BOTH = 'KEPT_BOTH', 'Kept Both'
        DISMISSED = 'DISMISSED', 'Dismissed'
    
    gedcom_import = models.ForeignKey(
        GedcomImport,
        on_delete=models.CASCADE,
        related_name="potential_duplicates",
        help_text="The import that found this duplicate"
    )
    existing_person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="duplicate_matches_existing",
        help_text="The existing person in database"
    )
    imported_person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="duplicate_matches_imported",
        help_text="The newly imported person"
    )
    confidence_score = models.FloatField(
        default=0,
        help_text="Match confidence score (0-100)"
    )
    match_reasons = models.TextField(
        blank=True,
        default="[]",
        help_text="JSON array of match reasons"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Review status"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_duplicates",
        help_text="User who reviewed this duplicate"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the duplicate was reviewed"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When duplicate was detected"
    )
    
    def __str__(self):
        return f"Duplicate: {self.existing_person.full_name} ↔ {self.imported_person.full_name} ({self.confidence_score:.0f}%)"
    
    @property
    def match_reasons_list(self):
        """Return match reasons as a Python list."""
        import json
        try:
            return json.loads(self.match_reasons) if self.match_reasons else []
        except json.JSONDecodeError:
            return []
    
    class Meta:
        verbose_name = "Potential Duplicate"
        verbose_name_plural = "Potential Duplicates"
        ordering = ['-confidence_score', '-created_at']


# =============================================================================
# Phase 8: DNA Assist Tools Models
# =============================================================================

class DNAKit(models.Model):
    """
    Represents a user's DNA test kit from various providers.
    
    Users can register their DNA kits and control privacy settings.
    By default, kits are private and not visible to others.
    
    Attributes:
        user (User): The kit owner
        provider (str): DNA testing provider (Ancestry, 23andMe, etc.)
        kit_id (str): Identifier from the provider
        display_name (str): User-friendly name for the kit
        is_private (bool): If True, kit is hidden from others (default True)
        allow_matching (bool): If True, allow DNA matching with others
        linked_person (Person): Optional link to a Person in family tree
        uploaded_at (datetime): When kit was registered
        notes (text): Private notes about the kit
    """
    
    class Provider(models.TextChoices):
        ANCESTRY = 'ANCESTRY', 'AncestryDNA'
        TWENTYTHREE = '23ANDME', '23andMe'
        FAMILYTREE = 'FTDNA', 'FamilyTreeDNA'
        MYHERITAGE = 'MYHERITAGE', 'MyHeritage'
        LIVINGDNA = 'LIVINGDNA', 'LivingDNA'
        GEDMATCH = 'GEDMATCH', 'GEDmatch'
        OTHER = 'OTHER', 'Other'
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dna_kits",
        help_text="Owner of this DNA kit"
    )
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.ANCESTRY,
        help_text="DNA testing provider"
    )
    kit_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Kit identifier from provider (optional)"
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Friendly name for this kit"
    )
    is_private = models.BooleanField(
        default=True,
        help_text="If True, kit is hidden from other users"
    )
    allow_matching = models.BooleanField(
        default=False,
        help_text="If True, allow DNA matching with other users"
    )
    linked_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dna_kits",
        help_text="Person in family tree this kit belongs to"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When kit was registered"
    )
    notes = models.TextField(
        blank=True,
        help_text="Private notes about this kit"
    )
    
    def __str__(self):
        return f"{self.display_name} ({self.get_provider_display()})"
    
    class Meta:
        verbose_name = "DNA Kit"
        verbose_name_plural = "DNA Kits"
        ordering = ['-uploaded_at']
        unique_together = [['user', 'provider', 'kit_id']]


class DNAMatch(models.Model):
    """
    Represents a DNA match between two users' kits.
    
    Stores the relationship details including shared cM (centiMorgans)
    and the predicted relationship range.
    
    Attributes:
        kit1 (DNAKit): First kit in the match
        kit2 (DNAKit): Second kit in the match
        shared_cm (float): Shared DNA in centiMorgans
        shared_segments (int): Number of shared DNA segments
        largest_segment (float): Largest shared segment in cM
        predicted_relationship (str): Estimated relationship
        confidence (str): Confidence level of prediction
        is_confirmed (bool): If both users confirmed the match
        discovered_at (datetime): When match was recorded
        notes (text): Notes about the match
    """
    
    class Confidence(models.TextChoices):
        HIGH = 'HIGH', 'High'
        MEDIUM = 'MEDIUM', 'Medium'
        LOW = 'LOW', 'Low'
    
    kit1 = models.ForeignKey(
        DNAKit,
        on_delete=models.CASCADE,
        related_name="matches_as_kit1",
        help_text="First kit in the match"
    )
    kit2 = models.ForeignKey(
        DNAKit,
        on_delete=models.CASCADE,
        related_name="matches_as_kit2",
        help_text="Second kit in the match"
    )
    shared_cm = models.FloatField(
        help_text="Shared DNA in centiMorgans"
    )
    shared_segments = models.PositiveIntegerField(
        default=0,
        help_text="Number of shared DNA segments"
    )
    largest_segment = models.FloatField(
        default=0,
        help_text="Largest shared segment in cM"
    )
    predicted_relationship = models.CharField(
        max_length=100,
        blank=True,
        help_text="Estimated relationship based on cM"
    )
    confidence = models.CharField(
        max_length=10,
        choices=Confidence.choices,
        default=Confidence.MEDIUM,
        help_text="Confidence level of prediction"
    )
    is_confirmed = models.BooleanField(
        default=False,
        help_text="Both users confirmed this match"
    )
    confirmed_by_kit1 = models.BooleanField(
        default=False,
        help_text="Kit1 owner confirmed"
    )
    confirmed_by_kit2 = models.BooleanField(
        default=False,
        help_text="Kit2 owner confirmed"
    )
    discovered_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When match was recorded"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this match"
    )
    
    def __str__(self):
        return f"{self.kit1.display_name} ↔ {self.kit2.display_name} ({self.shared_cm} cM)"
    
    def save(self, *args, **kwargs):
        # Auto-calculate predicted relationship based on cM
        if not self.predicted_relationship:
            self.predicted_relationship = self.calculate_relationship()
        # Update is_confirmed if both users confirmed
        self.is_confirmed = self.confirmed_by_kit1 and self.confirmed_by_kit2
        super().save(*args, **kwargs)
    
    def calculate_relationship(self):
        """
        Estimate relationship based on shared cM.
        
        Based on the Shared cM Project data:
        https://thegeneticgenealogist.com/2020/03/27/version-4-0-march-2020-update-to-the-shared-cm-project/
        """
        cm = self.shared_cm
        
        if cm >= 3400:
            return "Parent/Child or Full Sibling"
        elif cm >= 2300:
            return "Full Sibling"
        elif cm >= 1700:
            return "Grandparent/Grandchild, Half Sibling, or Aunt/Uncle"
        elif cm >= 1300:
            return "Half Sibling, Grandparent, or Aunt/Uncle"
        elif cm >= 900:
            return "Great-Grandparent, Half Aunt/Uncle, or 1st Cousin"
        elif cm >= 575:
            return "1st Cousin or Great-Aunt/Uncle"
        elif cm >= 340:
            return "1st Cousin once removed or Half 1st Cousin"
        elif cm >= 200:
            return "2nd Cousin or 1st Cousin twice removed"
        elif cm >= 100:
            return "2nd Cousin once removed or 3rd Cousin"
        elif cm >= 45:
            return "3rd Cousin or more distant"
        elif cm >= 20:
            return "4th Cousin or more distant"
        elif cm >= 6:
            return "5th-8th Cousin (distant)"
        else:
            return "Very distant or coincidental match"
    
    def get_relationship_confidence(self):
        """Determine confidence based on cM amount."""
        if self.shared_cm >= 400:
            return self.Confidence.HIGH
        elif self.shared_cm >= 90:
            return self.Confidence.MEDIUM
        else:
            return self.Confidence.LOW
    
    class Meta:
        verbose_name = "DNA Match"
        verbose_name_plural = "DNA Matches"
        ordering = ['-shared_cm']
        unique_together = [['kit1', 'kit2']]


class RelationshipSuggestion(models.Model):
    """
    Stores relationship suggestions based on DNA matches.
    
    When a DNA match is found, the system can suggest adding
    the matched person to the family tree. This model tracks
    those suggestions and the user's decisions.
    
    Attributes:
        dna_match (DNAMatch): The DNA match this suggestion is based on
        suggested_for_kit (DNAKit): Which kit owner receives the suggestion
        suggested_person (Person): Existing person in tree to link to (optional)
        suggested_relationship (str): Proposed relationship type
        status (str): Suggestion status
        family (FamilySpace): Family to add to
        reviewed_by (User): Who reviewed the suggestion
        reviewed_at (datetime): When reviewed
        notes (text): Notes about the decision
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'
        IGNORED = 'IGNORED', 'Ignored'
    
    dna_match = models.ForeignKey(
        DNAMatch,
        on_delete=models.CASCADE,
        related_name="suggestions",
        help_text="The DNA match this suggestion is based on"
    )
    suggested_for_kit = models.ForeignKey(
        DNAKit,
        on_delete=models.CASCADE,
        related_name="relationship_suggestions",
        help_text="Kit owner receiving this suggestion"
    )
    suggested_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dna_suggestions",
        help_text="Existing person to link with"
    )
    suggested_relationship = models.CharField(
        max_length=100,
        help_text="Suggested relationship type"
    )
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="dna_suggestions",
        help_text="Family space for this suggestion"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Suggestion status"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_dna_suggestions",
        help_text="User who reviewed this suggestion"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the suggestion was reviewed"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When suggestion was created"
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about the decision"
    )
    
    def __str__(self):
        return f"Suggestion: {self.suggested_relationship} for {self.suggested_for_kit.display_name}"
    
    class Meta:
        verbose_name = "Relationship Suggestion"
        verbose_name_plural = "Relationship Suggestions"
        ordering = ['-created_at']


class PersonClaim(models.Model):
    """
    Tracks when a user claims to be a Person in the family tree.
    
    Used for verification when a user's profile matches someone imported
    via GEDCOM or manually added. The user must verify their identity
    by confirming details like birth date, parents' names, etc.
    
    Workflow:
        1. User joins/views a family space
        2. System finds potential Person matches based on name
        3. PersonClaim created with status PENDING
        4. User reviews and confirms their details
        5. If details match, status becomes VERIFIED and membership linked
        6. If rejected/wrong person, status becomes REJECTED
    """
    
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Verification"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"
        EXPIRED = "EXPIRED", "Expired"
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="person_claims",
        help_text="User claiming this identity"
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="identity_claims",
        help_text="Person record being claimed"
    )
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="person_claims",
        help_text="Family space context"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Verification status"
    )
    
    # Verification data provided by user
    provided_birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Birth date provided by user for verification"
    )
    provided_birth_place = models.CharField(
        max_length=255,
        blank=True,
        help_text="Birth place provided for verification"
    )
    provided_mother_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Mother's name provided for verification"
    )
    provided_father_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Father's name provided for verification"
    )
    
    # Matching score and metadata
    name_match_score = models.FloatField(
        default=0.0,
        help_text="How closely the names matched (0-1)"
    )
    auto_matched = models.BooleanField(
        default=False,
        help_text="Whether this was auto-suggested based on name match"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    
    # Admin override
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_claims",
        help_text="Admin who verified/rejected (if manual)"
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        verbose_name = "Person Claim"
        verbose_name_plural = "Person Claims"
        ordering = ['-created_at']
        unique_together = ['user', 'person']  # User can only claim a person once
    
    def __str__(self):
        return f"{self.user.email} claims {self.person} ({self.status})"
    
    def verify_birth_date(self):
        """Check if provided birth date matches person's birth date."""
        if not self.provided_birth_date or not self.person.birth_date:
            return None  # Can't verify
        return self.provided_birth_date == self.person.birth_date
    
    def verify_parents(self):
        """Check if provided parent names match person's parents."""
        from django.db.models import Q
        
        # Get person's parents
        parent_rels = Relationship.objects.filter(
            person2=self.person,
            relationship_type=Relationship.Type.PARENT_CHILD
        ).select_related('person1')
        
        parents = {r.person1 for r in parent_rels}
        if not parents:
            return None  # No parents on record
        
        matches = 0
        checks = 0
        
        for parent in parents:
            parent_full_name = f"{parent.first_name} {parent.last_name}".lower()
            provided_name = self._get_provided_parent_name(parent.gender)
            if not provided_name:
                continue
            checks += 1
            if self._names_match(provided_name.lower(), parent_full_name):
                matches += 1
        
        return matches / checks if checks > 0 else None
    
    def _get_provided_parent_name(self, gender):
        """Get the provided parent name based on gender."""
        if gender == Person.Gender.MALE:
            return self.provided_father_name
        if gender == Person.Gender.FEMALE:
            return self.provided_mother_name
        return None
    
    @staticmethod
    def _names_match(name1, name2):
        """Check if two names match (either contains the other)."""
        return name1 in name2 or name2 in name1
    
    def calculate_verification_score(self):
        """
        Calculate overall verification confidence score.
        Returns a score from 0.0 to 1.0.
        """
        scores = []
        weights = []
        
        # Birth date match (highest weight)
        bd_match = self.verify_birth_date()
        if bd_match is not None:
            scores.append(1.0 if bd_match else 0.0)
            weights.append(0.5)
        
        # Parent name match
        parent_match = self.verify_parents()
        if parent_match is not None:
            scores.append(parent_match)
            weights.append(0.3)
        
        # Name similarity (already stored)
        scores.append(self.name_match_score)
        weights.append(0.2)
        
        if not weights:
            return 0.0
        
        # Weighted average
        total_weight = sum(weights)
        return sum(s * w for s, w in zip(scores, weights)) / total_weight
    
    def auto_verify_if_strong_match(self):
        """
        Automatically verify if the match is very strong.
        Requires: exact birth date match AND at least one parent match.
        """
        from django.utils import timezone
        
        bd_match = self.verify_birth_date()
        parent_match = self.verify_parents()
        
        # Strong match: exact birth date + at least 50% parent match
        if bd_match is True and (parent_match is None or parent_match >= 0.5):
            self.status = self.Status.VERIFIED
            self.verified_at = timezone.now()
            self.save()
            
            # Link to membership
            membership = Membership.objects.filter(
                user=self.user,
                family=self.family
            ).first()
            if membership and not membership.linked_person:
                membership.linked_person = self.person
                membership.save()
            
            return True
        return False


def _extract_user_name_from_model(user):
    """Extract first and last name from user model fields."""
    middle_name = ""
    maiden_name = ""
    try:
        middle_name = (user.profile.middle_name or '').lower().strip()
        maiden_name = (user.profile.maiden_name or '').lower().strip()
    except Exception:
        pass

    first_name = (user.first_name or '').lower().strip()
    if middle_name:
        first_name = " ".join(part for part in [first_name, middle_name] if part)

    return (
        first_name,
        (user.last_name or '').lower().strip(),
        maiden_name,
    )


def _extract_user_name_from_profile(user):
    """Extract first and last name from user profile display_name."""
    try:
        profile = user.profile
        if profile and profile.display_name:
            name_parts = profile.display_name.strip().split()
            if len(name_parts) >= 2:
                return " ".join(name_parts[:-1]).lower(), name_parts[-1].lower(), (profile.maiden_name or '').lower().strip()
            if len(name_parts) == 1:
                return name_parts[0].lower(), '', (profile.maiden_name or '').lower().strip()
    except Exception:
        pass
    return '', '', ''


def _extract_user_name_from_email(user):
    """Extract first and last name from user email prefix."""
    email_prefix = user.email.split('@')[0] if user.email else ''
    if '.' in email_prefix:
        parts = email_prefix.split('.')
        return parts[0].lower(), parts[-1].lower(), ''
    if '_' in email_prefix:
        parts = email_prefix.split('_')
        return parts[0].lower(), parts[-1].lower(), ''
    return email_prefix.lower(), '', ''


def _get_user_name(user):
    """Get user's first and last name from various sources."""
    user_first, user_last, user_maiden = _extract_user_name_from_model(user)
    if not user_first and not user_last and not user_maiden:
        user_first, user_last, user_maiden = _extract_user_name_from_profile(user)
    if not user_first and not user_last and not user_maiden:
        user_first, user_last, user_maiden = _extract_user_name_from_email(user)
    return user_first, user_last, user_maiden


def _calculate_name_match_score(user_first, user_last, user_maiden, person_first, person_last, person_maiden):
    """Calculate a weighted name similarity score."""
    from difflib import SequenceMatcher

    def _given_name_score(name1, name2):
        if not (name1 and name2):
            return 0

        normalized_1 = name1.strip().lower()
        normalized_2 = name2.strip().lower()
        score = SequenceMatcher(None, normalized_1, normalized_2).ratio()

        if normalized_1 == normalized_2:
            return 1.0

        if normalized_1.startswith(normalized_2 + " ") or normalized_2.startswith(normalized_1 + " "):
            score = max(score, 0.95)

        parts_1 = normalized_1.split()
        parts_2 = normalized_2.split()
        if parts_1 and parts_2 and parts_1[0] == parts_2[0]:
            score = max(score, 0.9)

        return score

    first_score = _given_name_score(user_first, person_first)
    user_last_candidates = [value for value in [user_last, user_maiden] if value]
    person_last_candidates = [value for value in [person_last, person_maiden] if value]

    last_score = 0
    for user_last_candidate in user_last_candidates:
        for person_last_candidate in person_last_candidates:
            last_score = max(
                last_score,
                SequenceMatcher(None, user_last_candidate, person_last_candidate).ratio(),
            )
    
    if user_first and user_last_candidates:
        return first_score * 0.4 + last_score * 0.6
    if user_last_candidates:
        return last_score * 0.8
    if user_first:
        return first_score * 0.6
    return 0


def find_matching_persons(user, family):
    """
    Find Person records that might match a user based on name.
    
    Args:
        user: User object with first_name, last_name
        family: FamilySpace to search in
    
    Returns:
        List of (Person, match_score) tuples, sorted by score descending
    """
    user_first, user_last, user_maiden = _get_user_name(user)
    
    if not user_first and not user_last and not user_maiden:
        return []
    
    matches = []
    for person in Person.objects.filter(family=family, is_deleted=False):
        if hasattr(person, 'linked_membership') and person.linked_membership.exists():
            continue
        
        person_first = (person.first_name or '').lower().strip()
        person_last = (person.last_name or '').lower().strip()
        person_maiden = (person.maiden_name or '').lower().strip()
        
        score = _calculate_name_match_score(
            user_first,
            user_last,
            user_maiden,
            person_first,
            person_last,
            person_maiden,
        )
        if score >= 0.7:
            matches.append((person, score))
    
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:5]


def create_auto_claim_for_user(user, family):
    """
    Automatically create a PersonClaim if a strong name match is found.
    Called when a user joins a family space.
    
    Returns the PersonClaim if created, None otherwise.
    """
    matches = find_matching_persons(user, family)
    
    if not matches:
        return None
    
    # Only auto-suggest if top match is very strong (>85%)
    top_person, top_score = matches[0]
    
    if top_score >= 0.85:
        # Check if claim already exists
        existing = PersonClaim.objects.filter(
            user=user,
            person=top_person
        ).first()
        
        if existing:
            return existing
        
        # Create new claim
        claim = PersonClaim.objects.create(
            user=user,
            person=top_person,
            family=family,
            name_match_score=top_score,
            auto_matched=True,
            status=PersonClaim.Status.PENDING
        )
        return claim
    
    return None


# =============================================================================
# Phase 9: Audit Trail and Data Protection
# =============================================================================

class AuditLog(models.Model):
    """
    Tracks all significant changes to family data for audit trail.
    
    Records who did what, when, and to what object. Used for:
    - Compliance and accountability
    - Recovering from mistakes
    - Understanding data history
    """
    
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Created'
        UPDATE = 'UPDATE', 'Updated'
        DELETE = 'DELETE', 'Deleted'
        RESTORE = 'RESTORE', 'Restored'
        IMPORT = 'IMPORT', 'Imported'
        EXPORT = 'EXPORT', 'Exported'
        MERGE = 'MERGE', 'Merged'
        CLAIM = 'CLAIM', 'Claimed Identity'
    
    class ObjectType(models.TextChoices):
        PERSON = 'PERSON', 'Person'
        RELATIONSHIP = 'RELATIONSHIP', 'Relationship'
        ALBUM = 'ALBUM', 'Album'
        PHOTO = 'PHOTO', 'Photo'
        EVENT = 'EVENT', 'Event'
        FAMILY = 'FAMILY', 'Family Space'
        GEDCOM = 'GEDCOM', 'GEDCOM Import'
        MEMBERSHIP = 'MEMBERSHIP', 'Membership'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        help_text="The family space this action was performed in"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_actions",
        help_text="User who performed this action"
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        help_text="Type of action performed"
    )
    object_type = models.CharField(
        max_length=20,
        choices=ObjectType.choices,
        help_text="Type of object affected"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the affected object"
    )
    object_repr = models.CharField(
        max_length=255,
        help_text="String representation of the object at time of action"
    )
    changes = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON dict of field changes (for updates)"
    )
    previous_data = models.JSONField(
        null=True,
        blank=True,
        help_text="JSON snapshot of object before deletion (for recovery)"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user"
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        help_text="Browser/client user agent"
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="When this action occurred"
    )
    
    def __str__(self):
        return f"{self.user} {self.action} {self.object_type} '{self.object_repr}' at {self.timestamp}"
    
    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['family', 'timestamp']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
        ]
    
    @classmethod
    def log(cls, family, user, action, obj, changes=None, previous_data=None, request=None):
        """
        Convenience method to create an audit log entry.
        
        Args:
            family: FamilySpace instance
            user: User who performed action
            action: AuditLog.Action choice
            obj: The affected model instance
            changes: Dict of changed fields (optional)
            previous_data: Dict of data before deletion (optional)
            request: HTTP request for IP/user agent (optional)
        """
        # Determine object type from model
        model_name = obj.__class__.__name__.upper()
        object_type = getattr(cls.ObjectType, model_name, cls.ObjectType.FAMILY)
        
        ip_address = None
        user_agent = ''
        if request:
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR', 
                         request.META.get('REMOTE_ADDR', '')).split(',')[0].strip() or None
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        return cls.objects.create(
            family=family,
            user=user,
            action=action,
            object_type=object_type,
            object_id=obj.pk,
            object_repr=str(obj)[:255],
            changes=changes,
            previous_data=previous_data,
            ip_address=ip_address,
            user_agent=user_agent
        )


class DeletionRequest(models.Model):
    """
    Tracks deletion requests that require admin approval.
    
    For critical data like Person records, this adds a review step
    before permanent deletion occurs.
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled by Requester'
    
    class ObjectType(models.TextChoices):
        PERSON = 'PERSON', 'Person'
        RELATIONSHIP = 'RELATIONSHIP', 'Relationship'
        ALBUM = 'ALBUM', 'Album'
        GEDCOM = 'GEDCOM', 'GEDCOM Import'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="deletion_requests",
        help_text="The family space this deletion is for"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deletion_requests_made",
        help_text="User who requested the deletion"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deletion_requests_reviewed",
        help_text="Admin who reviewed this request"
    )
    
    object_type = models.CharField(
        max_length=20,
        choices=ObjectType.choices,
        help_text="Type of object to delete"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the object to delete"
    )
    object_repr = models.CharField(
        max_length=255,
        help_text="String representation of the object"
    )
    object_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Snapshot of object data for review"
    )
    
    reason = models.TextField(
        blank=True,
        help_text="Reason for requesting deletion"
    )
    reviewer_notes = models.TextField(
        blank=True,
        help_text="Notes from the reviewer"
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current status of the request"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When deletion was requested"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the request was reviewed"
    )
    
    # If approved, should it be a permanent or soft delete?
    permanent_delete = models.BooleanField(
        default=False,
        help_text="If true, permanently delete. If false, soft delete."
    )
    
    def __str__(self):
        return f"Delete {self.object_type} '{self.object_repr}' - {self.status}"
    
    def approve(self, reviewer, notes=''):
        """Approve the deletion request and perform the deletion."""
        from django.utils import timezone
        
        self.reviewer = reviewer
        self.reviewer_notes = notes
        self.status = self.Status.APPROVED
        self.reviewed_at = timezone.now()
        self.save()
        
        # Perform the actual deletion
        if self.object_type == self.ObjectType.PERSON:
            try:
                person = Person.objects.get(pk=self.object_id)
                if self.permanent_delete:
                    person.delete()
                else:
                    person.soft_delete(reviewer)
            except Person.DoesNotExist:
                pass
        elif self.object_type == self.ObjectType.RELATIONSHIP:
            try:
                rel = Relationship.objects.get(pk=self.object_id)
                if self.permanent_delete:
                    rel.delete()
                else:
                    rel.soft_delete(reviewer)
            except Relationship.DoesNotExist:
                pass
    
    def reject(self, reviewer, notes=''):
        """Reject the deletion request."""
        from django.utils import timezone
        
        self.reviewer = reviewer
        self.reviewer_notes = notes
        self.status = self.Status.REJECTED
        self.reviewed_at = timezone.now()
        self.save()
    
    def cancel(self):
        """Cancel the deletion request (by requester)."""
        self.status = self.Status.CANCELLED
        self.save()
    
    class Meta:
        verbose_name = "Deletion Request"
        verbose_name_plural = "Deletion Requests"
        ordering = ['-created_at']


# =============================================================================
# Cross-Space Sharing Models
# =============================================================================

class SpaceAccessRequest(models.Model):
    """
    Request from a user to access another family's tree.
    
    Users can discover related family spaces and request view access.
    The target space's owners/admins can approve or deny requests.
    
    Attributes:
        requester (User): User requesting access
        target_family (FamilySpace): Family space they want to view
        message (str): Optional message explaining the request
        status (str): Pending, Approved, Denied
        reviewed_by (User): Admin who reviewed 
        reviewed_at (datetime): When reviewed
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        DENIED = 'DENIED', 'Denied'
        CANCELLED = 'CANCELLED', 'Cancelled'
    
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="space_access_requests_sent",
        help_text="User requesting access"
    )
    target_family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="access_requests",
        help_text="Family space being requested"
    )
    message = models.TextField(
        blank=True,
        max_length=500,
        help_text="Optional message to the family admins"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Request status"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_requests_reviewed",
        help_text="Admin who reviewed this request"
    )
    reviewer_notes = models.TextField(
        blank=True,
        max_length=500,
        help_text="Notes from the reviewer"
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the request was reviewed"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When request was created"
    )
    
    def approve(self, reviewer, notes=''):
        """Approve the access request and create SharedAccess."""
        from django.utils import timezone
        
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewer_notes = notes
        self.reviewed_at = timezone.now()
        self.save()
        
        # Create SharedAccess record
        SharedAccess.objects.get_or_create(
            user=self.requester,
            family=self.target_family,
            defaults={
                'granted_by': reviewer,
                'access_level': SharedAccess.AccessLevel.VIEWER,
            }
        )
    
    def deny(self, reviewer, notes=''):
        """Deny the access request."""
        from django.utils import timezone
        
        self.status = self.Status.DENIED
        self.reviewed_by = reviewer
        self.reviewer_notes = notes
        self.reviewed_at = timezone.now()
        self.save()
    
    def cancel(self):
        """Cancel a pending request (by requester)."""
        self.status = self.Status.CANCELLED
        self.save()
    
    def __str__(self):
        return f"{self.requester.email} → {self.target_family.name} ({self.status})"
    
    class Meta:
        verbose_name = "Space Access Request"
        verbose_name_plural = "Space Access Requests"
        ordering = ['-created_at']
        unique_together = [('requester', 'target_family')]


class SharedAccess(models.Model):
    """
    Grants a user read access to a family space they're not a member of.
    
    This allows cross-family tree viewing for collaborative genealogy.
    Shared users can view but not edit the family tree.
    
    Attributes:
        user (User): User who has shared access
        family (FamilySpace): Family space they can view
        access_level (str): Level of access (currently just viewer)
        granted_by (User): Who granted the access
        expires_at (datetime): Optional expiration date
    """
    
    class AccessLevel(models.TextChoices):
        VIEWER = 'VIEWER', 'View Only'
        LIMITED = 'LIMITED', 'Limited (ancestors only)'
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_family_access",
        help_text="User with shared access"
    )
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="shared_access_grants",
        help_text="Family space being shared"
    )
    access_level = models.CharField(
        max_length=20,
        choices=AccessLevel.choices,
        default=AccessLevel.VIEWER,
        help_text="Level of access granted"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="access_grants_given",
        help_text="User who granted the access"
    )
    granted_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When access was granted"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When access expires (null = never)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this access grant is currently active"
    )
    
    def is_valid(self):
        """Check if access is still valid."""
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True
    
    def revoke(self):
        """Revoke this access grant."""
        self.is_active = False
        self.save()
    
    def __str__(self):
        return f"{self.user.email} can view {self.family.name}"
    
    class Meta:
        verbose_name = "Shared Access"
        verbose_name_plural = "Shared Access Grants"
        unique_together = [('user', 'family')]
        ordering = ['-granted_at']


class CrossSpacePersonLink(models.Model):
    """
    Links the same person across different family spaces.
    
    When users discover that a person exists in multiple family trees,
    they can propose linking them. This enables collaborative genealogy
    and helps avoid duplicate research.
    
    Attributes:
        person1 (Person): Person in one family space
        person2 (Person): Same person in another space
        proposed_by (User): Who suggested the link
        status (str): Proposed, Confirmed, Rejected
        confidence_score (float): Match confidence
    """
    
    class Status(models.TextChoices):
        PROPOSED = 'PROPOSED', 'Proposed'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        REJECTED = 'REJECTED', 'Rejected'
    
    person1 = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="cross_space_links_as_person1",
        help_text="Person in one family space"
    )
    person2 = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="cross_space_links_as_person2",
        help_text="Same person in another family space"
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cross_space_links_proposed",
        help_text="User who proposed the link"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PROPOSED,
        help_text="Link status"
    )
    confidence_score = models.FloatField(
        default=0,
        help_text="Match confidence (0-100)"
    )
    match_reasons = models.TextField(
        blank=True,
        default="[]",
        help_text="JSON array explaining the match"
    )
    confirmed_by_space1 = models.BooleanField(
        default=False,
        help_text="Confirmed by person1's family admin"
    )
    confirmed_by_space2 = models.BooleanField(
        default=False,
        help_text="Confirmed by person2's family admin"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When link was proposed"
    )
    
    def confirm_for_space(self, family):
        """Confirm the link for one of the family spaces."""
        if self.person1.family == family:
            self.confirmed_by_space1 = True
        elif self.person2.family == family:
            self.confirmed_by_space2 = True
        
        # If both confirmed, mark as confirmed
        if self.confirmed_by_space1 and self.confirmed_by_space2:
            self.status = self.Status.CONFIRMED
        
        self.save()
    
    def __str__(self):
        return f"{self.person1.full_name} ↔ {self.person2.full_name} ({self.status})"
    
    class Meta:
        verbose_name = "Cross-Space Person Link"
        verbose_name_plural = "Cross-Space Person Links"
        ordering = ['-created_at']


class TreeMergeRequest(models.Model):
    """
    Request to merge persons from one family tree into another.
    
    This model tracks bulk merge operations where multiple persons
    from a source family can be copied/linked into a target family.
    Both family owners must approve the merge.
    
    Attributes:
        from_family (FamilySpace): Source family tree
        to_family (FamilySpace): Target family tree
        proposed_links (JSON): List of person matches to merge
        status (str): Request status
        requested_by (User): User who initiated the request
    """
    
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED_SOURCE = 'APPROVED_SOURCE', 'Approved by Source'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        COMPLETED = 'COMPLETED', 'Completed'
    
    from_family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="merge_requests_from",
        help_text="Source family tree"
    )
    to_family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        related_name="merge_requests_to",
        help_text="Target family tree"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="merge_requests_initiated",
        help_text="User who requested the merge"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Merge request status"
    )
    proposed_links = models.JSONField(
        default=list,
        help_text="JSON array of proposed person matches"
    )
    approved_by_source = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merge_requests_approved_source",
        help_text="Source family admin who approved"
    )
    approved_by_target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merge_requests_approved_target",
        help_text="Target family admin who approved"
    )
    merge_type = models.CharField(
        max_length=20,
        choices=[
            ('LINK', 'Link Only'),
            ('COPY', 'Copy Persons'),
        ],
        default='LINK',
        help_text="Whether to link or copy persons"
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about the merge"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def approve_by_source(self, user):
        """Approve the merge request on behalf of source family."""
        self.approved_by_source = user
        if self.status == self.Status.PENDING:
            self.status = self.Status.APPROVED_SOURCE
        self.save()
    
    def approve_by_target(self, user):
        """Approve the merge request on behalf of target family."""
        self.approved_by_target = user
        if self.approved_by_source:
            self.status = self.Status.APPROVED
        self.save()
    
    def reject(self):
        """Reject the merge request."""
        self.status = self.Status.REJECTED
        self.save()
    
    def complete(self):
        """Mark the merge as completed."""
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save()
    
    def __str__(self):
        return f"Merge: {self.from_family.name} → {self.to_family.name} ({self.status})"
    
    class Meta:
        verbose_name = "Tree Merge Request"
        verbose_name_plural = "Tree Merge Requests"
        ordering = ['-created_at']


# Custom manager for non-deleted objects
class ActivePersonManager(models.Manager):
    """Manager that returns only non-deleted persons."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class ActiveRelationshipManager(models.Manager):
    """Manager that returns only non-deleted relationships."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


# =============================================================================
# Phase 10: Prayer Requests & Testimonies
# =============================================================================

class PrayerRequest(models.Model):
    """
    A prayer request that can be posted anonymously or with identity.
    
    Users can share prayer needs with the community. Requests can be
    anonymous for sensitive matters. When prayers are answered, the
    requester can add a testimony.
    
    Attributes:
        family (FamilySpace): Optional - scoped to family or global
        author (User): User who posted (null if anonymous to others)
        title (str): Short title for the prayer request
        content (str): Full prayer request details
        is_anonymous (bool): Hide author identity from others
        status (str): Open, Answered, or Closed
        prayer_count (int): Number of people praying
        created_at (datetime): When request was posted
        updated_at (datetime): When request was last modified
    """
    
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open - Requesting Prayer'
        ANSWERED = 'ANSWERED', 'Answered - Praise Report'
        CLOSED = 'CLOSED', 'Closed'
    
    family = models.ForeignKey(
        FamilySpace,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="prayer_requests",
        help_text="Family space (null for global prayers)"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="prayer_requests",
        help_text="User who posted the request"
    )
    title = models.CharField(
        max_length=200,
        help_text="Short title for the prayer request"
    )
    content = models.TextField(
        help_text="Full prayer request details"
    )
    is_anonymous = models.BooleanField(
        default=False,
        help_text="Hide author identity from other users"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        help_text="Current status of the prayer request"
    )
    praying_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="prayers_committed",
        help_text="Users who committed to pray"
    )
    is_pinned = models.BooleanField(
        default=False,
        help_text="Pin to top of prayer list"
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hide from public view (moderation)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def prayer_count(self):
        """Number of users praying for this request."""
        return self.praying_users.count()
    
    @property
    def display_author(self):
        """Return author info or 'Anonymous' based on settings."""
        if self.is_anonymous or not self.author:
            return "Anonymous"
        return self.author.get_full_name() or self.author.email
    
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    class Meta:
        verbose_name = "Prayer Request"
        verbose_name_plural = "Prayer Requests"
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=['family', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]


class PrayerReply(models.Model):
    """
    A reply/comment on a prayer request.
    
    Allows community members to offer encouragement, scripture,
    or updates to prayer requests.
    
    Attributes:
        prayer_request (PrayerRequest): The prayer being replied to
        author (User): User who wrote the reply
        content (str): Reply text
        is_anonymous (bool): Hide author identity
        created_at (datetime): When reply was posted
    """
    
    prayer_request = models.ForeignKey(
        PrayerRequest,
        on_delete=models.CASCADE,
        related_name="replies",
        help_text="The prayer request this replies to"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="prayer_replies",
        help_text="User who wrote this reply"
    )
    content = models.TextField(
        max_length=2000,
        help_text="Reply content"
    )
    is_anonymous = models.BooleanField(
        default=False,
        help_text="Hide author identity"
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hide from view (moderation)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def display_author(self):
        """Return author info or 'Anonymous' based on settings."""
        if self.is_anonymous or not self.author:
            return "Anonymous"
        return self.author.get_full_name() or self.author.email
    
    def __str__(self):
        return f"Reply to '{self.prayer_request.title}' by {self.display_author}"
    
    class Meta:
        verbose_name = "Prayer Reply"
        verbose_name_plural = "Prayer Replies"
        ordering = ['created_at']


class PrayerTestimony(models.Model):
    """
    A testimony of answered prayer.
    
    When a prayer is marked as answered, the requester can share
    how God answered their prayer as encouragement to others.
    
    Attributes:
        prayer_request (PrayerRequest): The answered prayer (one-to-one)
        author (User): User who wrote the testimony
        content (str): The testimony/praise report
        is_anonymous (bool): Keep testimony anonymous
        answered_date (date): When the prayer was answered
        created_at (datetime): When testimony was posted
    """
    
    prayer_request = models.OneToOneField(
        PrayerRequest,
        on_delete=models.CASCADE,
        related_name="testimony",
        help_text="The prayer request this testimony is for"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="prayer_testimonies",
        help_text="User who wrote this testimony"
    )
    content = models.TextField(
        help_text="The testimony of how prayer was answered"
    )
    is_anonymous = models.BooleanField(
        default=False,
        help_text="Keep testimony anonymous"
    )
    answered_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the prayer was answered"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def display_author(self):
        """Return author info or 'Anonymous' based on settings."""
        if self.is_anonymous or not self.author:
            return "Anonymous"
        return self.author.get_full_name() or self.author.email
    
    def __str__(self):
        return f"Testimony: {self.prayer_request.title}"
    
    class Meta:
        verbose_name = "Prayer Testimony"
        verbose_name_plural = "Prayer Testimonies"
        ordering = ['-created_at']
