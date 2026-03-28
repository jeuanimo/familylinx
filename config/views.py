"""
Core Views

This module contains core views for the FamilyLinx application that don't
belong to any specific app (e.g., home page, landing page, contact page).
"""

import logging
import requests
from django import forms
from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings

logger = logging.getLogger(__name__)


class ContactForm(forms.Form):
    """Contact form for user inquiries."""
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your name'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@email.com'
        })
    )
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Subject'
        })
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Your message...',
            'rows': 5
        })
    )

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


CONTACT_EMAIL = "contact@fam-linx.org"


def contact(request):
    """
    Contact page with form to send messages to the FamilyLinx team.
    """
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name']
            email = form.cleaned_data['email']
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']
            
            # Compose email
            full_message = f"From: {name} <{email}>\n\n{message}"
            
            try:
                send_mail(
                    subject=f"[FamilyLinx Contact] {subject}",
                    message=full_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[CONTACT_EMAIL],
                    fail_silently=False,
                )
                messages.success(
                    request, 
                    "Thank you for your message! We'll get back to you soon."
                )
                return redirect('contact')
            except Exception as e:
                logger.error(f"Failed to send contact email: {str(e)}")
                messages.error(
                    request,
                    "Sorry, there was an error sending your message. "
                    "Please try again or email us directly at contact@fam-linx.org"
                )
    else:
        # Pre-fill form for authenticated users
        initial = {}
        if request.user.is_authenticated:
            initial['email'] = request.user.email
            if hasattr(request.user, 'profile'):
                initial['name'] = request.user.profile.get_display_name()
        form = ContactForm(initial=initial)
    
    return render(request, "contact.html", {
        'form': form,
        'contact_email': CONTACT_EMAIL,
    })
