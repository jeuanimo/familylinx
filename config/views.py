"""
Core Views

This module contains core views for the FamilyLinx application that don't
belong to any specific app (e.g., home page, landing page).
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def home(request):
    """
    Home page view.
    
    Shows landing page for anonymous users, dashboard for authenticated users.
    
    For authenticated users, displays:
    - List of family spaces they belong to
    - Pending invitations
    - Quick stats
    """
    if not request.user.is_authenticated:
        return render(request, 'landing.html')
    
    # Import here to avoid circular imports
    from families.models import Membership, Invite
    
    # Get user's family memberships
    memberships = Membership.objects.filter(
        user=request.user
    ).select_related('family').order_by('-joined_at')
    
    # Get pending invites for user's email
    pending_invites = Invite.objects.filter(
        email=request.user.email,
        accepted_at__isnull=True
    ).select_related('family')
    
    # Filter to only valid (non-expired) invites
    from django.utils import timezone
    pending_invites = [inv for inv in pending_invites if inv.is_valid]
    
    return render(request, 'home.html', {
        'memberships': memberships,
        'pending_invites': pending_invites,
    })
