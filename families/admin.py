"""
Families App - Admin Configuration

Register models for Django admin interface with customized display and filtering.
"""

from django.contrib import admin
from .models import (
    FamilySpace, Membership, Invite, Post, Comment, Event, RSVP, 
    Person, Relationship, Album, Photo, Notification, ChatMessage, 
    GedcomImport, PotentialDuplicate, DNAKit, DNAMatch, RelationshipSuggestion,
    FamilyKudos
)


@admin.register(FamilySpace)
class FamilySpaceAdmin(admin.ModelAdmin):
    """
    Admin configuration for FamilySpace model.
    """
    list_display = ('name', 'created_by', 'created_at', 'member_count')
    list_filter = ('created_at',)
    search_fields = ('name', 'description', 'created_by__email')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'created_by')
        }),
        ('Family Tree Anchors (Future)', {
            'fields': ('root_person_1_id', 'root_person_2_id'),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )
    
    def member_count(self, obj):
        """Return the number of members in this family space."""
        return obj.memberships.count()
    member_count.short_description = 'Members'


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    """
    Admin configuration for Membership model.
    """
    list_display = ('user', 'family', 'role', 'joined_at')
    list_filter = ('role', 'joined_at', 'family')
    search_fields = ('user__email', 'family__name')
    readonly_fields = ('joined_at',)
    raw_id_fields = ('user', 'family')
    
    fieldsets = (
        (None, {
            'fields': ('family', 'user', 'role')
        }),
        ('Metadata', {
            'fields': ('joined_at',),
        }),
    )


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    """
    Admin configuration for Invite model.
    """
    list_display = ('email', 'family', 'role', 'status', 'created_by', 'created_at', 'expires_at')
    list_filter = ('role', 'created_at', 'family')
    search_fields = ('email', 'family__name', 'created_by__email')
    readonly_fields = ('token', 'created_at', 'accepted_at')
    raw_id_fields = ('family', 'created_by')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('family', 'email', 'role')
        }),
        ('Invite Details', {
            'fields': ('token', 'created_by', 'expires_at'),
        }),
        ('Status', {
            'fields': ('created_at', 'accepted_at'),
        }),
    )
    
    def status(self, obj):
        """Return the invite status as a readable string."""
        if obj.accepted_at:
            return '✓ Accepted'
        elif obj.is_valid:
            return '⏳ Pending'
        else:
            return '✗ Expired'
    status.short_description = 'Status'


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """
    Admin configuration for Post model.
    """
    list_display = ('id', 'author', 'family', 'content_preview', 'has_image', 'is_pinned', 'is_hidden', 'created_at')
    list_filter = ('is_pinned', 'is_hidden', 'created_at', 'family')
    search_fields = ('content', 'author__email', 'family__name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('family', 'author')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('family', 'author', 'content', 'image')
        }),
        ('Status', {
            'fields': ('is_pinned', 'is_hidden'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    
    def content_preview(self, obj):
        """Return first 50 chars of content."""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
    
    def has_image(self, obj):
        """Return whether post has an image."""
        return bool(obj.image)
    has_image.boolean = True
    has_image.short_description = 'Image'


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    """
    Admin configuration for Comment model.
    """
    list_display = ('id', 'author', 'post_preview', 'content_preview', 'is_hidden', 'created_at')
    list_filter = ('is_hidden', 'created_at', 'post__family')
    search_fields = ('content', 'author__email', 'post__content')
    readonly_fields = ('created_at',)
    raw_id_fields = ('post', 'author')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('post', 'author', 'content')
        }),
        ('Status', {
            'fields': ('is_hidden',),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )
    
    def post_preview(self, obj):
        """Return first 30 chars of post content."""
        return obj.post.content[:30] + '...' if len(obj.post.content) > 30 else obj.post.content
    post_preview.short_description = 'Post'
    
    def content_preview(self, obj):
        """Return first 50 chars of comment content."""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Comment'


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """
    Admin configuration for Event model.
    """
    list_display = ('title', 'family', 'event_type', 'start_datetime', 'location', 'created_by', 'rsvp_count')
    list_filter = ('event_type', 'start_datetime', 'family')
    search_fields = ('title', 'description', 'location', 'family__name', 'created_by__email')
    readonly_fields = ('created_at',)
    raw_id_fields = ('family', 'created_by')
    date_hierarchy = 'start_datetime'
    
    fieldsets = (
        (None, {
            'fields': ('family', 'title', 'event_type')
        }),
        ('Date & Location', {
            'fields': ('start_datetime', 'end_datetime', 'location'),
        }),
        ('Details', {
            'fields': ('description',),
        }),
        ('Metadata', {
            'fields': ('created_by', 'created_at'),
        }),
    )
    
    def rsvp_count(self, obj):
        """Return count of RSVPs."""
        return obj.rsvps.count()
    rsvp_count.short_description = 'RSVPs'


@admin.register(FamilyKudos)
class FamilyKudosAdmin(admin.ModelAdmin):
    """Admin configuration for FamilyKudos model."""
    list_display = ("title", "family", "person", "created_by", "created_at")
    list_filter = ("family", "created_at")
    search_fields = ("title", "message", "family__name", "person__first_name", "person__last_name")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("family", "person", "created_by")


@admin.register(RSVP)
class RSVPAdmin(admin.ModelAdmin):
    """
    Admin configuration for RSVP model.
    """
    list_display = ('user', 'event', 'status', 'responded_at')
    list_filter = ('status', 'responded_at', 'event__family')
    search_fields = ('user__email', 'event__title')
    readonly_fields = ('responded_at',)
    raw_id_fields = ('event', 'user')
    
    fieldsets = (
        (None, {
            'fields': ('event', 'user', 'status')
        }),
        ('Metadata', {
            'fields': ('responded_at',),
        }),
    )


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """
    Admin configuration for Person model.
    """
    list_display = ('full_name', 'family', 'gender', 'birth_date', 'death_date', 'is_living')
    list_filter = ('gender', 'family', 'created_at')
    search_fields = ('first_name', 'last_name', 'maiden_name', 'family__name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('family', 'created_by', 'linked_user')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Name', {
            'fields': ('first_name', 'last_name', 'maiden_name', 'gender')
        }),
        ('Vital Information', {
            'fields': ('birth_date', 'birth_place', 'death_date', 'death_place'),
        }),
        ('Biography & Photo', {
            'fields': ('bio', 'photo'),
        }),
        ('Family Space', {
            'fields': ('family', 'linked_user', 'created_by'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Name'
    
    def is_living(self, obj):
        return obj.is_living
    is_living.boolean = True
    is_living.short_description = 'Living'


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    """
    Admin configuration for Relationship model.
    """
    list_display = ('__str__', 'family', 'relationship_type', 'start_date', 'end_date')
    list_filter = ('relationship_type', 'family')
    search_fields = ('person1__first_name', 'person1__last_name', 'person2__first_name', 'person2__last_name')
    readonly_fields = ('created_at',)
    raw_id_fields = ('family', 'person1', 'person2')
    
    fieldsets = (
        (None, {
            'fields': ('family', 'person1', 'person2', 'relationship_type')
        }),
        ('Details', {
            'fields': ('start_date', 'end_date', 'notes'),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    """
    Admin configuration for Album model.
    """
    list_display = ('title', 'family', 'created_by', 'photo_count', 'created_at')
    list_filter = ('created_at', 'family')
    search_fields = ('title', 'description', 'family__name', 'created_by__email')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('family', 'created_by', 'cover_photo')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('family', 'title', 'description')
        }),
        ('Cover & Creator', {
            'fields': ('cover_photo', 'created_by'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    
    def photo_count(self, obj):
        """Return the number of photos in this album."""
        return obj.photos.count()
    photo_count.short_description = 'Photos'


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    """
    Admin configuration for Photo model.
    """
    list_display = ('caption_display', 'album', 'uploaded_by', 'taken_date', 'tag_count', 'uploaded_at')
    list_filter = ('uploaded_at', 'album__family', 'album')
    search_fields = ('caption', 'taken_location', 'album__title', 'uploaded_by__email')
    readonly_fields = ('uploaded_at',)
    raw_id_fields = ('album', 'uploaded_by')
    filter_horizontal = ('tagged_people',)
    date_hierarchy = 'uploaded_at'
    
    fieldsets = (
        (None, {
            'fields': ('album', 'image', 'caption')
        }),
        ('Photo Details', {
            'fields': ('taken_date', 'taken_location'),
        }),
        ('Tagged People', {
            'fields': ('tagged_people',),
        }),
        ('Upload Info', {
            'fields': ('uploaded_by', 'uploaded_at'),
        }),
    )
    
    def caption_display(self, obj):
        """Return caption or a default."""
        return obj.caption[:50] + '...' if len(obj.caption) > 50 else obj.caption if obj.caption else '(No caption)'
    caption_display.short_description = 'Caption'
    
    def tag_count(self, obj):
        """Return the number of people tagged in this photo."""
        return obj.tagged_people.count()
    tag_count.short_description = 'Tagged'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Admin configuration for Notification model.
    """
    list_display = ('title', 'recipient', 'notification_type', 'family', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at', 'family')
    search_fields = ('title', 'message', 'recipient__email', 'family__name')
    readonly_fields = ('created_at',)
    raw_id_fields = ('recipient', 'family')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('recipient', 'family', 'notification_type')
        }),
        ('Content', {
            'fields': ('title', 'message', 'link'),
        }),
        ('Status', {
            'fields': ('is_read', 'created_at'),
        }),
    )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """
    Admin configuration for ChatMessage model.
    """
    list_display = ('content_preview', 'family', 'author', 'is_deleted', 'created_at')
    list_filter = ('is_deleted', 'created_at', 'family')
    search_fields = ('content', 'author__email', 'family__name')
    readonly_fields = ('created_at',)
    raw_id_fields = ('family', 'author')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('family', 'author')
        }),
        ('Message', {
            'fields': ('content', 'is_deleted'),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )
    
    def content_preview(self, obj):
        """Return truncated content."""
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'


# =============================================================================
# Phase 7: GEDCOM Import Models
# =============================================================================

@admin.register(GedcomImport)
class GedcomImportAdmin(admin.ModelAdmin):
    """
    Admin configuration for GedcomImport model.
    """
    list_display = ('file_name', 'family', 'status', 'persons_created', 'duplicates_found', 'uploaded_by', 'created_at')
    list_filter = ('status', 'created_at', 'family')
    search_fields = ('file_name', 'family__name', 'uploaded_by__email')
    readonly_fields = ('created_at', 'started_at', 'completed_at', 'persons_created', 
                       'persons_updated', 'relationships_created', 'duplicates_found', 'errors')
    raw_id_fields = ('family', 'uploaded_by')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('family', 'uploaded_by', 'file_name', 'file_size')
        }),
        ('Status', {
            'fields': ('status',),
        }),
        ('Statistics', {
            'fields': ('persons_created', 'persons_updated', 'relationships_created', 'duplicates_found'),
        }),
        ('Errors', {
            'fields': ('errors',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at'),
        }),
    )


@admin.register(PotentialDuplicate)
class PotentialDuplicateAdmin(admin.ModelAdmin):
    """
    Admin configuration for PotentialDuplicate model.
    """
    list_display = ('existing_person', 'imported_person', 'confidence_score', 'status', 'gedcom_import', 'reviewed_by')
    list_filter = ('status', 'created_at', 'gedcom_import__family')
    search_fields = ('existing_person__first_name', 'existing_person__last_name',
                     'imported_person__first_name', 'imported_person__last_name')
    readonly_fields = ('created_at', 'reviewed_at', 'confidence_score', 'match_reasons')
    raw_id_fields = ('gedcom_import', 'existing_person', 'imported_person', 'reviewed_by')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('gedcom_import', 'existing_person', 'imported_person')
        }),
        ('Match Details', {
            'fields': ('confidence_score', 'match_reasons'),
        }),
        ('Review', {
            'fields': ('status', 'reviewed_by', 'reviewed_at'),
        }),
        ('Metadata', {
            'fields': ('created_at',),
        }),
    )


# =============================================================================
# Phase 8: DNA Assist Models
# =============================================================================

@admin.register(DNAKit)
class DNAKitAdmin(admin.ModelAdmin):
    """
    Admin configuration for DNAKit model.
    """
    list_display = ('display_name', 'user', 'provider', 'kit_id', 'is_private', 'allow_matching', 'linked_person', 'uploaded_at')
    list_filter = ('provider', 'is_private', 'allow_matching', 'uploaded_at')
    search_fields = ('display_name', 'kit_id', 'user__email', 'linked_person__first_name', 'linked_person__last_name')
    readonly_fields = ('uploaded_at',)
    raw_id_fields = ('user', 'linked_person')
    date_hierarchy = 'uploaded_at'
    
    fieldsets = (
        (None, {
            'fields': ('user', 'display_name', 'provider', 'kit_id')
        }),
        ('Privacy Settings', {
            'fields': ('is_private', 'allow_matching'),
        }),
        ('Family Tree', {
            'fields': ('linked_person',),
        }),
        ('Additional Info', {
            'fields': ('notes', 'uploaded_at'),
        }),
    )


@admin.register(DNAMatch)
class DNAMatchAdmin(admin.ModelAdmin):
    """
    Admin configuration for DNAMatch model.
    """
    list_display = ('id', 'kit1', 'kit2', 'shared_cm', 'shared_segments', 'predicted_relationship', 'confidence', 'is_confirmed', 'discovered_at')
    list_filter = ('confidence', 'is_confirmed', 'discovered_at', 'confirmed_by_kit1', 'confirmed_by_kit2')
    search_fields = ('kit1__display_name', 'kit2__display_name', 'predicted_relationship')
    readonly_fields = ('discovered_at', 'predicted_relationship')
    raw_id_fields = ('kit1', 'kit2')
    date_hierarchy = 'discovered_at'
    
    fieldsets = (
        (None, {
            'fields': ('kit1', 'kit2')
        }),
        ('Match Data', {
            'fields': ('shared_cm', 'shared_segments', 'largest_segment'),
        }),
        ('Relationship', {
            'fields': ('predicted_relationship', 'confidence'),
        }),
        ('Confirmation', {
            'fields': ('is_confirmed', 'confirmed_by_kit1', 'confirmed_by_kit2'),
        }),
        ('Additional Info', {
            'fields': ('notes', 'discovered_at'),
        }),
    )


@admin.register(RelationshipSuggestion)
class RelationshipSuggestionAdmin(admin.ModelAdmin):
    """
    Admin configuration for RelationshipSuggestion model.
    """
    list_display = ('id', 'dna_match', 'suggested_for_kit', 'suggested_person', 'suggested_relationship', 'family', 'status', 'reviewed_by')
    list_filter = ('status', 'created_at', 'family')
    search_fields = ('suggested_for_kit__display_name', 'suggested_person__first_name', 'suggested_person__last_name', 'suggested_relationship')
    readonly_fields = ('created_at', 'reviewed_at')
    raw_id_fields = ('dna_match', 'suggested_for_kit', 'suggested_person', 'family', 'reviewed_by')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {
            'fields': ('dna_match', 'suggested_for_kit', 'suggested_person', 'family')
        }),
        ('Suggestion', {
            'fields': ('suggested_relationship',),
        }),
        ('Review', {
            'fields': ('status', 'reviewed_by', 'reviewed_at'),
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_at'),
        }),
    )
