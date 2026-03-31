"""
Accounts App - Models

User profile model for FamilyLinx with Facebook-style profile features.
"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """
    Extended user profile with Facebook-style features.
    
    Linked to family tree Person records to connect profile with genealogy.
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        help_text="User this profile belongs to"
    )
    
    # Profile display
    display_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name shown on profile (defaults to email username)"
    )
    middle_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Your middle name"
    )
    maiden_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Your maiden name"
    )
    bio = models.TextField(
        max_length=500,
        blank=True,
        help_text="Tell us about yourself"
    )
    
    # Profile images
    profile_picture = models.ImageField(
        upload_to='profiles/avatars/',
        blank=True,
        null=True,
        help_text="Profile picture (recommended: 180x180px)"
    )
    cover_photo = models.ImageField(
        upload_to='profiles/covers/',
        blank=True,
        null=True,
        help_text="Cover photo (recommended: 820x312px)"
    )
    
    # Personal info
    location = models.CharField(
        max_length=100,
        blank=True,
        help_text="Where you live"
    )
    website = models.URLField(
        blank=True,
        help_text="Your personal website"
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Your birth date"
    )
    
    # Privacy settings
    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public - Anyone can see'),
        ('MEMBERS', 'Family Members Only'),
        ('PRIVATE', 'Private - Only me'),
    ]
    profile_visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default='MEMBERS',
        help_text="Who can see your profile"
    )
    show_email = models.BooleanField(
        default=False,
        help_text="Show email address on profile"
    )
    show_birthday = models.BooleanField(
        default=True,
        help_text="Show birthday on profile"
    )
    
    # Family tree link
    linked_person = models.ForeignKey(
        'families.Person',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_profiles',
        help_text="Link this profile to a person in the family tree"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Online status tracking
    last_activity = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time the user was active on the site"
    )
    
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    
    def __str__(self):
        return f"{self.get_display_name()}'s Profile"

    def get_full_name(self):
        """Return the user's legal/profile name when available."""
        name_parts = [
            (self.user.first_name or "").strip(),
            (self.middle_name or "").strip(),
            (self.user.last_name or "").strip(),
        ]
        return " ".join(part for part in name_parts if part)
    
    def get_display_name(self):
        """Get display name, falling back to email username."""
        if self.display_name:
            return self.display_name
        full_name = self.get_full_name()
        if full_name:
            return full_name
        return self.user.email.split('@')[0]
    
    def get_profile_picture_url(self):
        """Get profile picture URL or default."""
        if self.profile_picture:
            return self.profile_picture.url
        return None
    
    def get_cover_photo_url(self):
        """Get cover photo URL or default."""
        if self.cover_photo:
            return self.cover_photo.url
        return None
    
    def is_online(self, threshold_minutes=5):
        """
        Check if user is currently online.
        
        Args:
            threshold_minutes: Number of minutes of inactivity before
                             considering user offline (default: 5)
        
        Returns:
            bool: True if user was active within threshold, False otherwise
        """
        if not self.last_activity:
            return False
        from django.utils import timezone
        from datetime import timedelta
        threshold = timezone.now() - timedelta(minutes=threshold_minutes)
        return self.last_activity >= threshold


class AdminAccessLog(models.Model):
    """Audit trail for Django admin login attempts and access blocks."""

    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Admin Login Success"
        LOGIN_FAILED = "LOGIN_FAILED", "Admin Login Failed"
        IP_BLOCKED = "IP_BLOCKED", "Admin IP Blocked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_access_logs",
        help_text="Authenticated user when the admin event succeeded.",
    )
    username = models.CharField(
        max_length=150,
        blank=True,
        help_text="Username or identifier used for the admin attempt.",
    )
    email = models.EmailField(
        blank=True,
        help_text="Email address associated with the admin attempt when known.",
    )
    ip_address = models.CharField(
        max_length=64,
        blank=True,
        help_text="Best-effort client IP address for the admin request.",
    )
    forwarded_for = models.CharField(
        max_length=255,
        blank=True,
        help_text="Raw X-Forwarded-For header for the admin request.",
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        help_text="Browser or client user agent string.",
    )
    path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Request path that triggered the admin event.",
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        db_index=True,
    )
    was_successful = models.BooleanField(
        default=False,
        help_text="Whether the admin access attempt succeeded.",
    )
    detail = models.CharField(
        max_length=255,
        blank=True,
        help_text="Extra diagnostic detail about the admin event.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Admin Access Log"
        verbose_name_plural = "Admin Access Logs"

    def __str__(self):
        label = self.username or self.email or "unknown"
        return f"{self.get_event_type_display()} - {label} - {self.created_at:%Y-%m-%d %H:%M:%S}"


class SiteAccessLog(models.Model):
    """Audit trail for site-wide sign-ins, failed auth, and signups."""

    class EventType(models.TextChoices):
        LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login Success"
        LOGIN_FAILED = "LOGIN_FAILED", "Login Failed"
        SIGNUP_CREATED = "SIGNUP_CREATED", "Signup Created"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_access_logs",
        help_text="Authenticated user associated with the event when known.",
    )
    username = models.CharField(
        max_length=150,
        blank=True,
        help_text="Username or identifier used for the site auth event.",
    )
    email = models.EmailField(
        blank=True,
        help_text="Email address associated with the auth event when known.",
    )
    ip_address = models.CharField(
        max_length=64,
        blank=True,
        help_text="Best-effort client IP address for the auth event.",
    )
    forwarded_for = models.CharField(
        max_length=255,
        blank=True,
        help_text="Raw X-Forwarded-For header for the auth event.",
    )
    user_agent = models.CharField(
        max_length=255,
        blank=True,
        help_text="Browser or client user agent string.",
    )
    path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Request path that triggered the auth event.",
    )
    event_type = models.CharField(
        max_length=20,
        choices=EventType.choices,
        db_index=True,
    )
    was_successful = models.BooleanField(
        default=False,
        help_text="Whether the auth event succeeded.",
    )
    detail = models.CharField(
        max_length=255,
        blank=True,
        help_text="Extra diagnostic detail about the auth event.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Site Access Log"
        verbose_name_plural = "Site Access Logs"

    def __str__(self):
        label = self.username or self.email or "unknown"
        return f"{self.get_event_type_display()} - {label} - {self.created_at:%Y-%m-%d %H:%M:%S}"


class ProfilePost(models.Model):
    """
    Posts on a user's profile wall (Facebook-style).
    """
    
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile_posts_authored',
        help_text="User who wrote the post"
    )
    profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='wall_posts',
        help_text="Profile this post is on"
    )
    
    content = models.TextField(
        max_length=2000,
        help_text="Post content"
    )
    image = models.ImageField(
        upload_to='profiles/posts/',
        blank=True,
        null=True,
        help_text="Optional image attachment"
    )
    video = models.FileField(
        upload_to='profiles/videos/',
        blank=True,
        null=True,
        help_text="Optional video attachment"
    )
    
    # Visibility
    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('MEMBERS', 'Family Members'),
        ('PRIVATE', 'Only Me'),
    ]
    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default='MEMBERS'
    )
    
    # Engagement
    is_pinned = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_pinned', '-created_at']
        verbose_name = "Profile Post"
        verbose_name_plural = "Profile Posts"
    
    def __str__(self):
        return f"Post by {self.author.email} on {self.profile}"


class ProfilePostComment(models.Model):
    """
    Comments on profile posts.
    """
    
    post = models.ForeignKey(
        ProfilePost,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile_post_comments'
    )
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.author.email} on post {self.post.id}"


class ProfileMessage(models.Model):
    """
    Direct messages between users (profile-based).
    """
    
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_profile_messages'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_profile_messages'
    )
    
    subject = models.CharField(max_length=200, blank=True)
    content = models.TextField(max_length=5000)
    
    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Soft delete
    deleted_by_sender = models.BooleanField(default=False)
    deleted_by_recipient = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Profile Message"
        verbose_name_plural = "Profile Messages"
    
    def __str__(self):
        return f"Message from {self.sender.email} to {self.recipient.email}"


class FriendRequest(models.Model):
    """
    Friend request between two users.

    At most one record per ordered pair (from_user, to_user).
    Use FriendRequest.get_between() to find the relationship regardless
    of direction.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        DECLINED = 'declined', 'Declined'

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_friend_requests',
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_friend_requests',
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['from_user', 'to_user']]
        verbose_name = 'Friend Request'
        verbose_name_plural = 'Friend Requests'

    def __str__(self):
        return f"{self.from_user} → {self.to_user} ({self.status})"

    @classmethod
    def get_between(cls, user_a, user_b):
        """Return the FriendRequest between two users (either direction), or None."""
        from django.db.models import Q
        return cls.objects.filter(
            Q(from_user=user_a, to_user=user_b) | Q(from_user=user_b, to_user=user_a)
        ).first()

    @classmethod
    def get_friends_for_user(cls, user):
        """Return list of User objects who are accepted friends with this user."""
        from django.db.models import Q
        accepted = cls.objects.filter(
            Q(from_user=user) | Q(to_user=user),
            status=cls.Status.ACCEPTED,
        ).select_related('from_user__profile', 'to_user__profile')
        return [
            req.to_user if req.from_user_id == user.pk else req.from_user
            for req in accepted
        ]


# Auto-create profile when user is created
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when a new User is created."""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    """Ensure UserProfile exists and save it."""
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
