"""
Accounts App - Views

Profile views for FamilyLinx with Facebook-style features.

This module implements user profile functionality including:
    - Profile viewing (own and other users')
    - Profile editing (display name, bio, location, etc.)
    - Profile and cover photo management with crop support
    - Wall posts (posting to user profiles)
    - Direct messaging between users
    - Linking profiles to family tree Person records

View Categories:
    Profile Management:
        - my_profile: Redirect to current user's profile
        - profile_view: Display a user's profile with wall posts
        - profile_edit: Edit own profile settings
        - profile_picture_update: Upload/crop profile picture
        - cover_photo_update: Upload/crop cover photo
        
    Wall Posts:
        - wall_post_create: Create a post on a profile wall
        - wall_post_edit: Edit your own wall post
        - wall_post_delete: Delete your own wall post
        - wall_post_comment: Add comment to a wall post
        - wall_comment_delete: Delete your own comment
        
    Messaging:
        - message_inbox: View received messages
        - message_sent: View sent messages
        - message_compose: Write a new message
        - message_view: View a specific message
        - message_delete: Delete a message
        
    Family Tree Linking:
        - link_to_tree: Link profile to a Person in family tree
        - unlink_from_tree: Remove family tree link
        - get_family_persons: API endpoint for person dropdown

Security:
    - All views require authentication (@login_required)
    - Profile visibility settings control who can view profiles
    - Users can only edit their own profiles, posts, and comments
    - Message privacy enforced (only sender/recipient can view)
"""

import base64
import uuid
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Q, Count
from django.db.models.functions import Coalesce
from django.core.files.base import ContentFile
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from allauth.account.forms import LoginForm, SignupForm
from allauth.account.internal import flows as account_flows
from allauth.core.exceptions import ImmediateHttpResponse

from .models import UserProfile, ProfilePost, ProfilePostComment, ProfileMessage
from .forms import (
    UserProfileForm, ProfilePictureForm, CoverPhotoForm,
    ProfilePostForm, ProfilePostCommentForm, ProfileMessageForm
)
from utils.image_utils import process_cropped_image

User = get_user_model()


def _get_safe_next_url(request, default=None):
    """Return a same-site redirect target from GET/POST next params."""
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default


def _get_or_create_profile(user):
    """Helper to ensure user has a profile."""
    profile, created = UserProfile.objects.get_or_create(user=user)
    return profile


def _shared_family_ids_by_user_ids(user_ids):
    """Return a mapping of user_id -> set of family ids."""
    from families.models import Membership

    family_ids_by_user = {user_id: set() for user_id in user_ids}
    memberships = Membership.objects.filter(user_id__in=user_ids).values_list("user_id", "family_id")
    for user_id, family_id in memberships:
        family_ids_by_user.setdefault(user_id, set()).add(family_id)
    return family_ids_by_user


def _can_view_profile(viewer, profile_user, profile, shared_families):
    """Enforce profile visibility rules."""
    if viewer == profile_user:
        return True
    if profile.profile_visibility == "PUBLIC":
        return True
    if profile.profile_visibility == "MEMBERS":
        return bool(shared_families)
    return False


def _ensure_site_admin(request):
    """Require a Django staff/superuser account."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("You do not have access to this page.")


@never_cache
@sensitive_post_parameters("password", "password1", "password2")
def auth_portal(request):
    """Combined sign-in and sign-up page for FamilyLinx."""
    redirect_url = _get_safe_next_url(request, default="/")
    if request.user.is_authenticated:
        return redirect(redirect_url)

    active_mode = request.GET.get("mode", "login")
    login_form = LoginForm(request=request)
    signup_form = SignupForm()

    if request.method == "POST":
        action = request.POST.get("auth_action")
        if action == "signup":
            active_mode = "signup"
            signup_form = SignupForm(request.POST)
            if signup_form.is_valid():
                user, response = signup_form.try_save(request)
                if response:
                    return response
                try:
                    return account_flows.signup.complete_signup(
                        request,
                        user=user,
                        redirect_url=redirect_url,
                        by_passkey=getattr(signup_form, "by_passkey", False),
                    )
                except ImmediateHttpResponse as exc:
                    return exc.response
            login_form = LoginForm(request=request)
        else:
            active_mode = "login"
            login_form = LoginForm(request.POST, request=request)
            if login_form.is_valid():
                try:
                    return login_form.login(request, redirect_url=redirect_url)
                except ImmediateHttpResponse as exc:
                    return exc.response
            signup_form = SignupForm()

    return render(
        request,
        "accounts/auth_portal.html",
        {
            "login_form": login_form,
            "signup_form": signup_form,
            "active_mode": active_mode,
            "next_url": redirect_url,
        },
    )


@login_required
def my_profile(request):
    """
    Redirect to current user's profile.
    """
    return redirect('accounts:profile_view', user_id=request.user.id)


@login_required
def profile_view(request, user_id):
    """
    View a user's profile (Facebook-style wall).
    """
    from families.models import Membership, DNAKit

    profile_user = get_object_or_404(User, id=user_id)
    profile = _get_or_create_profile(profile_user)
    
    is_own_profile = request.user == profile_user

    user_families = set(Membership.objects.filter(user=request.user).values_list("family_id", flat=True))
    profile_families = set(Membership.objects.filter(user=profile_user).values_list("family_id", flat=True))
    shared_families = user_families & profile_families
    
    # Check visibility
    if not _can_view_profile(request.user, profile_user, profile, shared_families):
        privacy_title = "This Profile is Private"
        privacy_message = f"{profile.get_display_name()} has set their profile to private."
        if profile.profile_visibility == "MEMBERS":
            privacy_title = "Family Members Only"
            privacy_message = (
                f"{profile.get_display_name()} only shares this profile with people who "
                f"share a family space."
            )
        return render(request, 'accounts/profile_private.html', {
            'profile_user': profile_user,
            'profile': profile,
            'privacy_title': privacy_title,
            'privacy_message': privacy_message,
        })
    # Get wall posts
    posts = profile.wall_posts.all()
    if not is_own_profile:
        posts = posts.exclude(visibility='PRIVATE')
    
    chat_family_id = None
    if shared_families:
        chat_family_id = next(iter(shared_families))
    elif is_own_profile and user_families:
        chat_family_id = next(iter(user_families))
    
    # Get DNA kits for this user (only visible on own profile or if public)
    dna_kits = []
    if is_own_profile:
        dna_kits = DNAKit.objects.filter(user=profile_user).order_by('-uploaded_at')[:5]
    else:
        # Only show non-private kits to others
        dna_kits = DNAKit.objects.filter(user=profile_user, is_private=False).order_by('-uploaded_at')[:5]
    
    # Post form for own profile or commenting
    post_form = ProfilePostForm() if is_own_profile else None
    comment_form = ProfilePostCommentForm()
    
    context = {
        'profile_user': profile_user,
        'profile': profile,
        'is_own_profile': is_own_profile,
        'posts': posts,
        'post_form': post_form,
        'comment_form': comment_form,
        'shared_families': shared_families,
        'dna_kits': dna_kits,
        'chat_family_id': chat_family_id,
    }
    
    return render(request, 'accounts/profile_view.html', context)


@login_required
def user_directory(request):
    """
    Directory of users who have logged into the site.
    """
    query = request.GET.get("q", "").strip()

    profiles = (
        UserProfile.objects
        .filter(user__last_login__isnull=False)
        .select_related("user", "linked_person")
        .annotate(last_seen=Coalesce("last_activity", "user__last_login"))
        .order_by("-last_seen", "user__date_joined")
    )

    if query:
        profiles = profiles.filter(
            Q(display_name__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(middle_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(maiden_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__username__icontains=query)
        )

    profiles = list(profiles)
    user_ids = [request.user.id] + [profile.user_id for profile in profiles]
    family_ids_by_user = _shared_family_ids_by_user_ids(user_ids)
    viewer_family_ids = family_ids_by_user.get(request.user.id, set())

    for profile in profiles:
        shared_families = viewer_family_ids & family_ids_by_user.get(profile.user_id, set())
        profile.shared_family_count = len(shared_families)
        profile.can_view_profile = _can_view_profile(request.user, profile.user, profile, shared_families)
        profile.directory_email = profile.user.email if (profile.user == request.user or profile.show_email) else ""

    return render(request, "accounts/user_directory.html", {
        "profiles": profiles,
        "query": query,
    })


@login_required
def admin_user_directory(request):
    """
    Staff-only view of all site accounts and profiles.
    """
    _ensure_site_admin(request)

    query = request.GET.get("q", "").strip()
    active_since = timezone.now() - timezone.timedelta(days=7)

    profiles = (
        UserProfile.objects
        .select_related("user", "linked_person")
        .annotate(
            last_seen=Coalesce("last_activity", "user__last_login"),
            family_count=Count("user__memberships", distinct=True),
            wall_post_count=Count("wall_posts", distinct=True),
        )
        .order_by("-created_at")
    )

    if query:
        profiles = profiles.filter(
            Q(display_name__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(middle_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(maiden_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__username__icontains=query)
        )

    profiles = list(profiles)
    for profile in profiles:
        profile.has_logged_in = bool(profile.user.last_login)
        profile.recently_active = bool(profile.last_seen and profile.last_seen >= active_since)

    profile_summary = {
        "total_accounts": len(profiles),
        "logged_in_accounts": sum(1 for profile in profiles if profile.has_logged_in),
        "never_logged_in_accounts": sum(1 for profile in profiles if not profile.has_logged_in),
        "recently_active_accounts": sum(1 for profile in profiles if profile.recently_active),
        "staff_accounts": sum(1 for profile in profiles if profile.user.is_staff or profile.user.is_superuser),
    }

    return render(request, "accounts/admin_user_directory.html", {
        "profiles": profiles,
        "query": query,
        "profile_summary": profile_summary,
    })


@login_required
def profile_edit(request):
    """
    Edit own profile.
    """
    profile = _get_or_create_profile(request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('accounts:profile_view', user_id=request.user.id)
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'accounts/profile_edit.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def profile_picture_update(request):
    """
    Quick update profile picture with cropping support.
    """
    profile = _get_or_create_profile(request.user)
    
    if request.method == 'POST':
        # Check for cropped image data first
        content_file, filename = process_cropped_image(request)
        
        if content_file and filename:
            # Save cropped image
            profile.profile_picture.save(filename, content_file, save=True)
            messages.success(request, "Profile picture updated!")
            return redirect('accounts:profile_view', user_id=request.user.id)
        else:
            # Fallback to regular form upload
            form = ProfilePictureForm(request.POST, request.FILES, instance=profile)
            if form.is_valid():
                form.save()
                messages.success(request, "Profile picture updated!")
                return redirect('accounts:profile_view', user_id=request.user.id)
    else:
        form = ProfilePictureForm(instance=profile)
    
    return render(request, 'accounts/profile_picture_update.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def cover_photo_update(request):
    """
    Quick update cover photo with cropping support.
    """
    profile = _get_or_create_profile(request.user)
    
    if request.method == 'POST':
        # Check for cropped image data from global cropper
        content_file, filename = process_cropped_image(request)
        
        # Also check for old 'cropped_image' field (from custom cropper)
        if not content_file:
            cropped_data = request.POST.get('cropped_image', '')
            if cropped_data and cropped_data.startswith('data:image'):
                try:
                    format_prefix, imgstr = cropped_data.split(';base64,')
                    ext = format_prefix.split('/')[-1]
                    if ext == 'jpeg':
                        ext = 'jpg'
                    image_data = base64.b64decode(imgstr)
                    filename = f"cover_{request.user.id}_{uuid.uuid4().hex[:8]}.{ext}"
                    content_file = ContentFile(image_data)
                except Exception as e:
                    messages.error(request, f"Error processing image: {str(e)}")
        
        if content_file and filename:
            profile.cover_photo.save(filename, content_file, save=True)
            messages.success(request, "Cover photo updated!")
            return redirect('accounts:profile_view', user_id=request.user.id)
        else:
            # Fallback to regular file upload
            form = CoverPhotoForm(request.POST, request.FILES, instance=profile)
            if form.is_valid():
                form.save()
                messages.success(request, "Cover photo updated!")
                return redirect('accounts:profile_view', user_id=request.user.id)
    else:
        form = CoverPhotoForm(instance=profile)
    
    return render(request, 'accounts/cover_photo_update.html', {
        'form': form,
        'profile': profile,
    })


# =============================================================================
# Wall Posts
# =============================================================================

@login_required
def wall_post_create(request, user_id):
    """
    Create a post on someone's wall.
    """
    profile_user = get_object_or_404(User, id=user_id)
    profile = _get_or_create_profile(profile_user)
    
    # Only allow posting on own wall for now
    if request.user != profile_user:
        messages.error(request, "You can only post on your own wall.")
        return redirect('accounts:profile_view', user_id=user_id)
    
    if request.method == 'POST':
        form = ProfilePostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.profile = profile
            post.save()
            messages.success(request, "Post created!")
            return redirect('accounts:profile_view', user_id=user_id)
    
    return redirect('accounts:profile_view', user_id=user_id)


@login_required
def wall_post_edit(request, post_id):
    """
    Edit a wall post.
    """
    post = get_object_or_404(ProfilePost, id=post_id)
    
    # Only author can edit
    if post.author != request.user:
        messages.error(request, "You can only edit your own posts.")
        return redirect('accounts:profile_view', user_id=post.profile.user.id)
    
    if request.method == 'POST':
        form = ProfilePostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Post updated!")
            return redirect('accounts:profile_view', user_id=post.profile.user.id)
    else:
        form = ProfilePostForm(instance=post)
    
    return render(request, 'accounts/wall_post_edit.html', {
        'form': form,
        'post': post,
    })


@login_required
def wall_post_delete(request, post_id):
    """
    Delete a wall post.
    """
    post = get_object_or_404(ProfilePost, id=post_id)
    profile_user_id = post.profile.user.id
    
    # Author or profile owner can delete
    if post.author != request.user and post.profile.user != request.user:
        messages.error(request, "You cannot delete this post.")
        return redirect('accounts:profile_view', user_id=profile_user_id)
    
    if request.method == 'POST':
        post.delete()
        messages.success(request, "Post deleted!")
        return redirect('accounts:profile_view', user_id=profile_user_id)
    
    return render(request, 'accounts/wall_post_delete.html', {
        'post': post,
    })


@login_required
def wall_post_comment(request, post_id):
    """
    Add a comment to a wall post.
    """
    post = get_object_or_404(ProfilePost, id=post_id)
    
    if request.method == 'POST':
        form = ProfilePostCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()
            messages.success(request, "Comment added!")
    
    return redirect('accounts:profile_view', user_id=post.profile.user.id)


@login_required
def wall_comment_delete(request, comment_id):
    """
    Delete a comment.
    """
    comment = get_object_or_404(ProfilePostComment, id=comment_id)
    profile_user_id = comment.post.profile.user.id
    
    # Author or post author can delete
    if comment.author != request.user and comment.post.author != request.user:
        messages.error(request, "You cannot delete this comment.")
        return redirect('accounts:profile_view', user_id=profile_user_id)
    
    if request.method == 'POST':
        comment.delete()
        messages.success(request, "Comment deleted!")
    
    return redirect('accounts:profile_view', user_id=profile_user_id)


# =============================================================================
# Messages
# =============================================================================

@login_required
def message_inbox(request):
    """
    View message inbox.
    """
    messages_list = ProfileMessage.objects.filter(
        recipient=request.user,
        deleted_by_recipient=False
    ).select_related('sender')
    
    unread_count = messages_list.filter(is_read=False).count()
    
    return render(request, 'accounts/message_inbox.html', {
        'messages_list': messages_list,
        'unread_count': unread_count,
    })


@login_required
def message_sent(request):
    """
    View sent messages.
    """
    messages_list = ProfileMessage.objects.filter(
        sender=request.user,
        deleted_by_sender=False
    ).select_related('recipient')
    
    return render(request, 'accounts/message_sent.html', {
        'messages_list': messages_list,
    })


@login_required
def message_compose(request, recipient_id=None):
    """
    Compose a new message.
    """
    recipient = None
    if recipient_id:
        recipient = get_object_or_404(User, id=recipient_id)
    
    if request.method == 'POST':
        form = ProfileMessageForm(request.POST)
        recipient_id = request.POST.get('recipient_id')
        
        if recipient_id:
            recipient = get_object_or_404(User, id=recipient_id)
        
        if form.is_valid() and recipient:
            msg = form.save(commit=False)
            msg.sender = request.user
            msg.recipient = recipient
            msg.save()
            messages.success(request, f"Message sent to {recipient.email}!")
            return redirect('accounts:message_inbox')
    else:
        form = ProfileMessageForm()
    
    return render(request, 'accounts/message_compose.html', {
        'form': form,
        'recipient': recipient,
    })


@login_required
def message_view(request, message_id):
    """
    View a single message.
    """
    msg = get_object_or_404(ProfileMessage, id=message_id)
    
    # Must be sender or recipient
    if msg.sender != request.user and msg.recipient != request.user:
        raise Http404("Message not found")
    
    # Mark as read if recipient viewing
    if msg.recipient == request.user and not msg.is_read:
        msg.is_read = True
        msg.read_at = timezone.now()
        msg.save()
    
    return render(request, 'accounts/message_view.html', {
        'msg': msg,
    })


@login_required
def message_delete(request, message_id):
    """
    Delete a message (soft delete).
    """
    msg = get_object_or_404(ProfileMessage, id=message_id)
    
    if request.method == 'POST':
        if msg.sender == request.user:
            msg.deleted_by_sender = True
            msg.save()
            messages.success(request, "Message deleted from sent.")
        elif msg.recipient == request.user:
            msg.deleted_by_recipient = True
            msg.save()
            messages.success(request, "Message deleted from inbox.")
        else:
            messages.error(request, "Cannot delete this message.")
        
        return redirect('accounts:message_inbox')
    
    return render(request, 'accounts/message_delete.html', {
        'msg': msg,
    })


# =============================================================================
# Family Tree Linking
# =============================================================================

@login_required
def link_to_tree(request):
    """
    Link profile to a person in the family tree.
    """
    from families.models import Membership, Person, FamilySpace
    
    profile = _get_or_create_profile(request.user)
    
    # Get user's families
    memberships = Membership.objects.filter(user=request.user).select_related('family')
    families = [m.family for m in memberships]
    
    if request.method == 'POST':
        family_id = request.POST.get('family_id')
        person_id = request.POST.get('person_id')
        
        if family_id and person_id:
            # Verify access
            if not Membership.objects.filter(user=request.user, family_id=family_id).exists():
                messages.error(request, "Access denied.")
                return redirect('accounts:my_profile')
            
            person = get_object_or_404(Person, id=person_id, family_id=family_id)
            profile.linked_person = person
            profile.save()
            messages.success(request, f"Linked your profile to {person.full_name} in the family tree!")
            return redirect('accounts:my_profile')
    
    return render(request, 'accounts/link_to_tree.html', {
        'profile': profile,
        'families': families,
    })


@login_required
def unlink_from_tree(request):
    """
    Remove link to family tree person.
    """
    profile = _get_or_create_profile(request.user)
    
    if request.method == 'POST':
        profile.linked_person = None
        profile.save()
        messages.success(request, "Unlinked from family tree.")
    
    return redirect('accounts:my_profile')


@login_required
def get_family_persons(request, family_id):
    """
    AJAX endpoint to get persons in a family for linking.
    """
    from families.models import Membership, Person
    
    # Verify access
    if not Membership.objects.filter(user=request.user, family_id=family_id).exists():
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    persons = Person.objects.filter(family_id=family_id).order_by('last_name', 'first_name')
    
    data = [{
        'id': p.id,
        'name': p.full_name,
        'birth_year': p.birth_date.year if p.birth_date else None,
    } for p in persons]
    
    return JsonResponse({'persons': data})
