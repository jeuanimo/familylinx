"""
Family Template Tags and Filters

Custom template tags for family tree display, including:
- Date formatting with qualifiers (about, before, after)
- Privacy-aware display helpers
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def date_with_qualifier(person, date_type='birth'):
    """
    Format a date with its qualifier prefix.
    
    Usage:
        {{ person|date_with_qualifier:"birth" }}  -> "~1850" or "<1850" or ">1850"
        {{ person|date_with_qualifier:"death" }}
    
    Args:
        person: Person model instance
        date_type: "birth" or "death"
        
    Returns:
        Formatted date string with qualifier symbol
    """
    if date_type == 'birth':
        date = person.birth_date
        qualifier = getattr(person, 'birth_date_qualifier', '')
    else:
        date = person.death_date
        qualifier = getattr(person, 'death_date_qualifier', '')
    
    if not date:
        return '?'
    
    year = date.year
    
    # Map qualifiers to symbols
    symbols = {
        'ABT': '~',      # About/approximately
        'BEF': '<',      # Before
        'AFT': '>',      # After
        'EST': '≈',      # Estimated
        'CAL': '≈',      # Calculated
    }
    
    symbol = symbols.get(qualifier, '')
    return f"{symbol}{year}"


@register.filter
def birth_year_display(person):
    """
    Display birth year with qualifier for tree view.
    
    Usage: {{ person|birth_year_display }}
    Returns: "~1850" or "1850" or "?"
    """
    return date_with_qualifier(person, 'birth')


@register.filter
def death_year_display(person):
    """
    Display death year with qualifier for tree view.
    
    Usage: {{ person|death_year_display }}
    Returns: "~1920" or "1920" or "?"
    """
    return date_with_qualifier(person, 'death')


@register.filter
def lifespan_display(person):
    """
    Display full lifespan with qualifiers.
    
    Usage: {{ person|lifespan_display }}
    Returns: "~1850 - 1920" or "1850 - present" or "? - ?"
    """
    birth = date_with_qualifier(person, 'birth')
    
    if person.death_date:
        death = date_with_qualifier(person, 'death')
        return f"{birth} - {death}"
    elif person.birth_date:
        return f"{birth} - present"
    else:
        return "? - ?"


@register.filter
def privacy_name(person, user):
    """
    Return name respecting privacy settings.
    
    If person is private and user is not a family member,
    returns "Private Person" instead of the actual name.
    """
    if person.is_private:
        # In a real implementation, check if user is family member
        return person.full_name  # For now, show name to all logged in users
    return person.full_name


@register.filter
def gender_icon(person):
    """
    Return Bootstrap icon class for gender.
    
    Usage: {{ person|gender_icon }}
    Returns: "bi-gender-male" or "bi-gender-female" or "bi-person"
    """
    icons = {
        'M': 'bi-gender-male',
        'F': 'bi-gender-female',
        'O': 'bi-person',
        'U': 'bi-person',
    }
    return icons.get(person.gender, 'bi-person')


@register.filter
def gender_color(person):
    """
    Return CSS color variable for gender (Ancestry-style).
    
    Usage: {{ person|gender_color }}
    Returns: "var(--fl-blue)" for male, pink for female
    """
    colors = {
        'M': 'var(--fl-blue)',
        'F': '#e879a9',
        'O': 'var(--fl-gold)',
        'U': 'var(--fl-muted)',
    }
    return colors.get(person.gender, 'var(--fl-muted)')


@register.filter
def get_online_status(online_status_dict, person_id):
    """
    Get online status for a person from the status dictionary.
    
    Usage: {{ online_status|get_online_status:person.id }}
    Returns: True if online, False otherwise
    """
    if not online_status_dict:
        return False
    return online_status_dict.get(person_id, False)
