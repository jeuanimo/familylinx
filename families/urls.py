"""
Families App - URL Configuration

This module defines URL patterns for the families application.
All URLs are namespaced under 'families' for reverse URL lookup.

URL Patterns:
    /families/create/                    - Create a new family space
    /families/<id>/                       - View family space details
    /families/<id>/invites/new/           - Create new invitation
    /families/invite/<token>/accept/      - Accept an invitation

Namespace:
    Use 'families:name' for reverse URL lookup.
    Example: reverse('families:family_detail', kwargs={'family_id': 1})

Security Notes:
    - All views require authentication (enforced in views)
    - family_id uses int converter (prevents injection)
    - token uses str converter (no SQL involved in lookup)
"""

from django.urls import path
from . import views

# Namespace for reverse URL lookups (e.g., 'families:family_detail')
app_name = "families"

urlpatterns = [
    # Family Space Management
    # -----------------------
    
    # Create a new family space
    # Access: Any authenticated user
    path("create/", views.family_create, name="family_create"),
    
    # View family space details, members, and invites
    # Access: Family members only
    path("<int:family_id>/", views.family_detail, name="family_detail"),
    
    # Delete a family space
    # Access: OWNER role only
    path("<int:family_id>/delete/", views.family_delete, name="family_delete"),
    
    # Invitation Management
    # ---------------------
    
    # Create a new invitation for a family space
    # Access: OWNER and ADMIN roles only
    path("<int:family_id>/invites/new/", views.invite_create, name="invite_create"),
    
    # Accept an invitation via secure token
    # Access: Any authenticated user with valid token
    path("invite/<str:token>/accept/", views.invite_accept, name="invite_accept"),
    
    # ==========================================================================
    # Phase 2: Social Feed URLs
    # ==========================================================================
    
    # Create a new post in the family feed
    path("<int:family_id>/posts/new/", views.post_create, name="post_create"),
    
    # View single post with comments
    path("<int:family_id>/posts/<int:post_id>/", views.post_detail, name="post_detail"),

    # Like/unlike a post
    path("<int:family_id>/posts/<int:post_id>/like/", views.post_like_toggle, name="post_like_toggle"),
    
    # Delete a post (author or admin)
    path("<int:family_id>/posts/<int:post_id>/delete/", views.post_delete, name="post_delete"),
    
    # Hide/unhide a post (moderation - admin only)
    path("<int:family_id>/posts/<int:post_id>/hide/", views.post_hide, name="post_hide"),
    
    # Delete a comment
    path("<int:family_id>/posts/<int:post_id>/comments/<int:comment_id>/delete/", 
         views.comment_delete, name="comment_delete"),
    
    # ==========================================================================
    # Phase 3: Events & Calendar URLs
    # ==========================================================================
    
    # List all events for a family
    path("<int:family_id>/events/", views.event_list, name="event_list"),
    path("<int:family_id>/search/", views.family_search, name="family_search"),
    
    # Create a new event
    path("<int:family_id>/events/new/", views.event_create, name="event_create"),
    
    # View event details and RSVPs
    path("<int:family_id>/events/<int:event_id>/", views.event_detail, name="event_detail"),
    
    # Edit an event
    path("<int:family_id>/events/<int:event_id>/edit/", views.event_edit, name="event_edit"),
    
    # Delete an event
    path("<int:family_id>/events/<int:event_id>/delete/", views.event_delete, name="event_delete"),
    
    # RSVP to an event
    path("<int:family_id>/events/<int:event_id>/rsvp/", views.event_rsvp, name="event_rsvp"),
    
    # ==========================================================================
    # Phase 4: Family Tree URLs
    # ==========================================================================
    
    # Family tree visualization
    path("<int:family_id>/tree/", views.family_tree, name="family_tree"),
    path("<int:family_id>/tree/interactive/", views.family_tree_interactive, name="family_tree_interactive"),
    path("<int:family_id>/tree/link-me/", views.link_to_tree, name="link_to_tree"),
    
    # Identity verification (link GEDCOM person to user account)
    path("<int:family_id>/tree/find-me/", views.find_my_match, name="find_my_match"),
    path("<int:family_id>/tree/claim/<int:person_id>/", views.claim_identity, name="claim_identity"),
    path("<int:family_id>/tree/verify/<int:claim_id>/", views.verify_identity, name="verify_identity"),
    path("<int:family_id>/tree/my-claims/", views.my_claims, name="my_claims"),
    
    # Family tree data API (JSON)
    path("<int:family_id>/tree/data/", views.family_tree_data, name="family_tree_data"),
    
    # GEDCOM import
    path("<int:family_id>/tree/import/", views.gedcom_import, name="gedcom_import"),
    path("<int:family_id>/tree/import/<int:import_id>/report/", views.gedcom_import_report, name="gedcom_import_report"),
    path("<int:family_id>/tree/import/<int:import_id>/rollback/", views.gedcom_import_rollback, name="gedcom_import_rollback"),
    path("<int:family_id>/tree/import/<int:import_id>/delete/", views.gedcom_import_delete, name="gedcom_import_delete"),
    path("<int:family_id>/tree/import/history/", views.gedcom_import_history, name="gedcom_import_history"),
    path("<int:family_id>/tree/duplicates/", views.duplicate_queue, name="duplicate_queue"),
    path("<int:family_id>/tree/duplicates/bulk-delete-perfect/", views.bulk_delete_perfect_duplicates, name="bulk_delete_perfect_duplicates"),
    path("<int:family_id>/tree/duplicates/<int:duplicate_id>/", views.duplicate_review, name="duplicate_review"),
    
    # Person management
    path("<int:family_id>/people/", views.person_list, name="person_list"),
    path("<int:family_id>/people/new/", views.person_create, name="person_create"),
    path("<int:family_id>/people/<int:person_id>/", views.person_detail, name="person_detail"),
    path("<int:family_id>/people/<int:person_id>/edit/", views.person_edit, name="person_edit"),
    path("<int:family_id>/people/<int:person_id>/delete/", views.person_delete, name="person_delete"),
    path("<int:family_id>/people/<int:person_id>/add-ancestor/", views.add_ancestor, name="add_ancestor"),
    path("<int:family_id>/people/<int:person_id>/add-child/", views.add_child, name="add_child"),
    
    # Relationship management
    path("<int:family_id>/people/<int:person_id>/relationships/add/", views.relationship_add, name="relationship_add"),
    path("<int:family_id>/relationships/<int:relationship_id>/delete/", views.relationship_delete, name="relationship_delete"),
    
    # ==========================================================================
    # Phase 5: Photo Album URLs
    # ==========================================================================
    
    # Album management
    path("<int:family_id>/albums/", views.album_list, name="album_list"),
    path("<int:family_id>/albums/new/", views.album_create, name="album_create"),
    path("<int:family_id>/albums/<int:album_id>/", views.album_detail, name="album_detail"),
    path("<int:family_id>/albums/<int:album_id>/edit/", views.album_edit, name="album_edit"),
    path("<int:family_id>/albums/<int:album_id>/delete/", views.album_delete, name="album_delete"),
    
    # Photo management
    path("<int:family_id>/albums/<int:album_id>/upload/", views.photo_upload, name="photo_upload"),
    path("<int:family_id>/albums/<int:album_id>/photos/<int:photo_id>/", views.photo_detail, name="photo_detail"),
    path("<int:family_id>/albums/<int:album_id>/photos/<int:photo_id>/edit/", views.photo_edit, name="photo_edit"),
    path("<int:family_id>/albums/<int:album_id>/photos/<int:photo_id>/delete/", views.photo_delete, name="photo_delete"),
    path("<int:family_id>/albums/<int:album_id>/photos/<int:photo_id>/set-cover/", views.photo_set_cover, name="photo_set_cover"),
    path("<int:family_id>/albums/<int:album_id>/photos/<int:photo_id>/suggest-tags/", views.photo_tag_suggestions, name="photo_tag_suggestions"),
    
    # ==========================================================================
    # Phase 6: Notifications & Messaging URLs
    # ==========================================================================
    
    # Notifications
    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/<int:notification_id>/read/", views.notification_mark_read, name="notification_mark_read"),
    path("notifications/mark-all-read/", views.notification_mark_all_read, name="notification_mark_all_read"),
    path("notifications/dropdown/", views.notification_dropdown, name="notification_dropdown"),
    
    # Unified Messaging
    path("<int:family_id>/messages/", views.messaging_hub, name="messaging_hub"),
    path("<int:family_id>/messages/direct/<int:user_id>/", views.direct_conversation_start, name="direct_conversation_start"),
    path("<int:family_id>/messages/branch/<int:person_id>/", views.branch_conversation_start, name="branch_conversation_start"),
    path("<int:family_id>/messages/event/<int:event_id>/", views.event_conversation_start, name="event_conversation_start"),
    path("<int:family_id>/messages/conversations/<int:conversation_id>/", views.conversation_room, name="conversation_room"),
    path("<int:family_id>/messages/conversations/<int:conversation_id>/messages/<int:message_id>/delete/", views.conversation_message_delete, name="conversation_message_delete"),

    # Legacy Family Group Chat route
    path("<int:family_id>/chat/", views.chat_room, name="chat_room"),
    path("<int:family_id>/chat/messages/", views.chat_messages_json, name="chat_messages_json"),
    path("<int:family_id>/chat/<int:message_id>/delete/", views.chat_delete_message, name="chat_delete_message"),
    
    # ==========================================================================
    # Phase 8: DNA Assist Tools URLs
    # ==========================================================================
    
    # DNA Kit Management
    path("dna/", views.dna_kit_list, name="dna_kit_list"),
    path("dna/kits/new/", views.dna_kit_create, name="dna_kit_create"),
    path("dna/kits/<int:kit_id>/", views.dna_kit_detail, name="dna_kit_detail"),
    path("dna/kits/<int:kit_id>/edit/", views.dna_kit_edit, name="dna_kit_edit"),
    path("dna/kits/<int:kit_id>/delete/", views.dna_kit_delete, name="dna_kit_delete"),
    path("dna/kits/<int:kit_id>/link/<int:family_id>/", views.dna_link_to_person, name="dna_link_to_person"),
    
    # DNA Match Management
    path("dna/matches/", views.dna_match_list, name="dna_match_list"),
    path("dna/kits/<int:kit_id>/matches/new/", views.dna_match_create, name="dna_match_create"),
    path("dna/matches/<int:match_id>/", views.dna_match_detail, name="dna_match_detail"),
    path("dna/matches/<int:match_id>/confirm/", views.dna_match_confirm, name="dna_match_confirm"),
    
    # Relationship Suggestions (Attach-to-Tree Workflow)
    path("dna/suggestions/", views.relationship_suggestion_list, name="relationship_suggestion_list"),
    path("dna/suggestions/<int:suggestion_id>/", views.relationship_suggestion_review, name="relationship_suggestion_review"),
    
    # DNA Connections Visualization
    path("dna/connections/", views.dna_connections, name="dna_connections"),
    
    # ==========================================================================
    # Phase 9: Trash Bin, Audit Trail & Data Protection URLs
    # ==========================================================================
    
    # Trash Bin (soft-deleted items)
    path("<int:family_id>/trash/", views.trash_bin, name="trash_bin"),
    path("<int:family_id>/trash/empty/", views.empty_trash, name="empty_trash"),
    path("<int:family_id>/trash/person/<int:person_id>/restore/", views.restore_person, name="restore_person"),
    path("<int:family_id>/trash/person/<int:person_id>/permanent-delete/", views.permanent_delete_person, name="permanent_delete_person"),
    path("<int:family_id>/trash/relationship/<int:relationship_id>/restore/", views.restore_relationship, name="restore_relationship"),
    
    # Audit Log
    path("<int:family_id>/audit-log/", views.audit_log, name="audit_log"),
    
    # Deletion Requests (approval workflow)
    path("<int:family_id>/deletion-requests/", views.deletion_request_list, name="deletion_request_list"),
    path("<int:family_id>/my-deletion-requests/", views.my_deletion_requests, name="my_deletion_requests"),
    path("<int:family_id>/request-deletion/<str:object_type>/<int:object_id>/", views.deletion_request_create, name="deletion_request_create"),
    path("<int:family_id>/deletion-requests/<int:request_id>/review/", views.deletion_request_review, name="deletion_request_review"),
    
    # ==========================================================================
    # Phase 10: Living Museum URLs
    # ==========================================================================
    
    # Museum home - browse all memories for a family
    path("<int:family_id>/museum/", views.museum_home, name="museum_home"),
    
    # Museum for a specific person
    path("<int:family_id>/museum/person/<int:person_id>/", views.museum_person, name="museum_person"),
    
    # Memory CRUD
    path("<int:family_id>/museum/memory/new/", views.memory_create, name="memory_create"),
    path("<int:family_id>/museum/memory/new/<int:person_id>/", views.memory_create, name="memory_create_for_person"),
    path("<int:family_id>/museum/memory/<int:memory_id>/", views.memory_detail, name="memory_detail"),
    path("<int:family_id>/museum/memory/<int:memory_id>/edit/", views.memory_edit, name="memory_edit"),
    path("<int:family_id>/museum/memory/<int:memory_id>/delete/", views.memory_delete, name="memory_delete"),
    
    # Memory interactions
    path("<int:family_id>/museum/memory/<int:memory_id>/react/", views.memory_react, name="memory_react"),
    path("<int:family_id>/museum/memory/<int:memory_id>/comment/", views.memory_comment, name="memory_comment"),
    path("<int:family_id>/museum/memory/<int:memory_id>/media/<int:media_id>/delete/", views.memory_media_delete, name="memory_media_delete"),
    # Life Story & Time Capsules
    path("<int:family_id>/museum/person/<int:person_id>/life-story/", views.life_story, name="life_story"),
    path("<int:family_id>/time-capsules/", views.time_capsule_list, name="time_capsule_list"),
    path("<int:family_id>/time-capsules/new/", views.time_capsule_create, name="time_capsule_create"),
    path("<int:family_id>/time-capsules/<int:capsule_id>/", views.time_capsule_detail, name="time_capsule_detail"),
    path("<int:family_id>/person/<int:person_id>/chatbot/", views.person_chatbot, name="person_chatbot"),
    
    # ==========================================================================
    # Museum Sharing URLs
    # ==========================================================================
    
    # Create a share link
    path("<int:family_id>/museum/share/create/", views.museum_share_create, name="museum_share_create"),
    path("<int:family_id>/museum/share/create/<str:share_type>/<int:object_id>/", views.museum_share_create, name="museum_share_create_object"),
    
    # List shares (for admins)
    path("<int:family_id>/museum/shares/", views.museum_share_list, name="museum_share_list"),
    
    # Delete/revoke a share
    path("<int:family_id>/museum/share/<int:share_id>/delete/", views.museum_share_delete, name="museum_share_delete"),
    
    # View shared content (public - no login required)
    path("shared/<str:share_token>/", views.museum_shared_view, name="museum_shared_view"),
    
    # My shares dashboard
    path("museum/my-shares/", views.museum_my_shares, name="museum_my_shares"),
]
