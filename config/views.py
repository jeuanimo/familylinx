"""
Core Views

This module contains core views for the FamilyLinx application that don't
belong to any specific app (e.g., home page, landing page).
"""

import requests
from django.shortcuts import render

VERSE_OF_THE_DAY_URL = "https://beta.ourmanna.com/api/v1/get?format=json&order=daily"
FALLBACK_VERSE = {
    "text": "Thy word is a lamp unto my feet, and a light unto my path.",
    "reference": "Psalm 119:105",
    "version": "KJV",
}


def get_word_of_the_day():
    """
    Fetch the daily verse from Our Manna, falling back to a local verse if the
    remote API is unavailable or returns an unexpected payload.
    """
    try:
        response = requests.get(
            VERSE_OF_THE_DAY_URL,
            headers={"Accept": "application/json"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        verse_details = data["verse"]["details"]
        return {
            "text": verse_details["text"],
            "reference": verse_details["reference"],
            "version": verse_details["version"],
            "is_fallback": False,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {
            **FALLBACK_VERSE,
            "is_fallback": True,
        }


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


def gods_word_of_day(request):
    """
    Public page that highlights the current verse of the day.
    """
    return render(request, "gods_word_of_day.html", get_word_of_the_day())
