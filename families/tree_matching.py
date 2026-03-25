"""
Tree Matching Utilities

Algorithms for finding potential duplicate persons across family trees.
Used to facilitate tree linking and merging operations.
"""

import json
import re
from difflib import SequenceMatcher
from django.db.models import Q

from .models import Person, CrossSpacePersonLink


def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ""
    # Lowercase, remove extra spaces, remove common suffixes
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    # Remove common suffixes
    suffixes = [' jr', ' sr', ' ii', ' iii', ' iv', ' jr.', ' sr.']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name


def soundex(name):
    """
    Generate Soundex code for a name.
    Useful for matching names that sound similar but are spelled differently.
    """
    if not name:
        return ""
    
    name = name.upper()
    # Keep first letter
    soundex_code = name[0]
    
    # Mapping for Soundex
    mapping = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
    }
    
    prev_code = mapping.get(name[0], '')
    
    for char in name[1:]:
        code = mapping.get(char, '')
        if code and code != prev_code:
            soundex_code += code
        prev_code = code if code else prev_code
        
        if len(soundex_code) >= 4:
            break
    
    # Pad with zeros
    soundex_code = soundex_code.ljust(4, '0')
    return soundex_code[:4]


def name_similarity(person1, person2):
    """
    Calculate name similarity score between two persons.
    Returns a score from 0 to 1.
    """
    score = 0
    reasons = []
    
    # Compare each name component
    score, reasons = _compare_first_names(person1, person2, score, reasons)
    score, reasons = _compare_last_names(person1, person2, score, reasons)
    score, reasons = _compare_maiden_names(person1, person2, score, reasons)
    
    return min(score, 1.0), reasons


def _compare_first_names(person1, person2, score, reasons):
    """Compare first names and update score."""
    fn1 = normalize_name(person1.first_name)
    fn2 = normalize_name(person2.first_name)
    if fn1 and fn2:
        fn_ratio = SequenceMatcher(None, fn1, fn2).ratio()
        score += fn_ratio * 0.3
        if fn_ratio > 0.8:
            reasons.append(f"First names similar: {person1.first_name} ≈ {person2.first_name}")
    return score, reasons


def _compare_last_names(person1, person2, score, reasons):
    """Compare last names with Soundex bonus."""
    ln1 = normalize_name(person1.last_name)
    ln2 = normalize_name(person2.last_name)
    if not (ln1 and ln2):
        return score, reasons
    
    ln_ratio = SequenceMatcher(None, ln1, ln2).ratio()
    score += ln_ratio * 0.4
    
    if ln_ratio > 0.8:
        reasons.append(f"Last names similar: {person1.last_name} ≈ {person2.last_name}")
    
    # Soundex bonus for last name
    if soundex(ln1) == soundex(ln2):
        score += 0.1
        if ln_ratio < 0.8:
            reasons.append("Last names sound similar (Soundex match)")
    
    return score, reasons


def _compare_maiden_names(person1, person2, score, reasons):
    """Compare maiden names if both exist."""
    if not (person1.maiden_name and person2.maiden_name):
        return score, reasons
    
    mn1 = normalize_name(person1.maiden_name)
    mn2 = normalize_name(person2.maiden_name)
    mn_ratio = SequenceMatcher(None, mn1, mn2).ratio()
    score += mn_ratio * 0.2
    
    if mn_ratio > 0.8:
        reasons.append(f"Maiden names match: {person1.maiden_name} ≈ {person2.maiden_name}")
    
    return score, reasons


def date_proximity(person1, person2):
    """
    Calculate date proximity score.
    Returns a score from 0 to 1 based on birth/death date closeness.
    """
    score = 0
    reasons = []
    
    # Birth date comparison
    if person1.birth_date and person2.birth_date:
        year_diff = abs(person1.birth_date.year - person2.birth_date.year)
        if year_diff == 0:
            score += 0.5
            reasons.append(f"Same birth year: {person1.birth_date.year}")
        elif year_diff <= 2:
            score += 0.4
            reasons.append(f"Birth years within 2 years: {person1.birth_date.year} vs {person2.birth_date.year}")
        elif year_diff <= 5:
            score += 0.2
    
    # Death date comparison
    if person1.death_date and person2.death_date:
        year_diff = abs(person1.death_date.year - person2.death_date.year)
        if year_diff == 0:
            score += 0.5
            reasons.append(f"Same death year: {person1.death_date.year}")
        elif year_diff <= 2:
            score += 0.4
            reasons.append(f"Death years within 2 years: {person1.death_date.year} vs {person2.death_date.year}")
        elif year_diff <= 5:
            score += 0.2
    
    # Both living or both deceased
    if person1.is_living == person2.is_living:
        score += 0.1
    
    return min(score, 1.0), reasons


def place_similarity(person1, person2):
    """
    Calculate place similarity score.
    Returns a score from 0 to 1.
    """
    score = 0
    reasons = []
    
    def compare_places(p1, p2, label):
        nonlocal score, reasons
        if p1 and p2:
            p1_lower = p1.lower().strip()
            p2_lower = p2.lower().strip()
            ratio = SequenceMatcher(None, p1_lower, p2_lower).ratio()
            if ratio > 0.7:
                score += 0.5
                reasons.append(f"{label} similar: {p1} ≈ {p2}")
            elif ratio > 0.5:
                score += 0.25
    
    compare_places(person1.birth_place, person2.birth_place, "Birth places")
    compare_places(person1.death_place, person2.death_place, "Death places")
    
    return min(score, 1.0), reasons


def gender_match(person1, person2):
    """Check if genders match."""
    if person1.gender and person2.gender:
        if person1.gender == person2.gender:
            return 1.0, ["Same gender"]
        else:
            return 0, ["Different genders - likely not the same person"]
    return 0.5, []  # Unknown gender, neutral score


def calculate_match_score(person1, person2):
    """
    Calculate overall match score between two persons.
    Returns tuple of (score 0-100, list of reasons).
    """
    all_reasons = []
    
    # Weight factors
    name_weight = 0.40
    date_weight = 0.30
    place_weight = 0.15
    gender_weight = 0.15
    
    # Calculate component scores
    name_score, name_reasons = name_similarity(person1, person2)
    date_score, date_reasons = date_proximity(person1, person2)
    place_score, place_reasons = place_similarity(person1, person2)
    gender_score, gender_reasons = gender_match(person1, person2)
    
    all_reasons.extend(name_reasons)
    all_reasons.extend(date_reasons)
    all_reasons.extend(place_reasons)
    all_reasons.extend(gender_reasons)
    
    # Gender mismatch is a deal-breaker
    if gender_score == 0:
        return 0, gender_reasons
    
    # Calculate weighted score
    total_score = (
        name_score * name_weight +
        date_score * date_weight +
        place_score * place_weight +
        gender_score * gender_weight
    )
    
    # Convert to 0-100 scale
    final_score = round(total_score * 100)
    
    return final_score, all_reasons


def find_potential_matches(person, target_family, threshold=40):
    """
    Find potential matches for a person in another family tree.
    
    Args:
        person: The Person to match
        target_family: The FamilySpace to search in
        threshold: Minimum score (0-100) to include in results
    
    Returns:
        List of tuples: (matched_person, score, reasons)
    """
    # Get candidates from target family
    candidates = Person.objects.filter(
        family=target_family,
        is_deleted=False
    )
    
    # Exclude persons already linked to this person
    existing_links = CrossSpacePersonLink.objects.filter(
        Q(person1=person) | Q(person2=person),
        status__in=['PROPOSED', 'CONFIRMED']
    ).values_list('person1_id', 'person2_id')
    
    linked_ids = set()
    for p1_id, p2_id in existing_links:
        linked_ids.add(p1_id)
        linked_ids.add(p2_id)
    
    candidates = candidates.exclude(id__in=linked_ids)
    
    matches = []
    for candidate in candidates:
        score, reasons = calculate_match_score(person, candidate)
        if score >= threshold:
            matches.append({
                'person': candidate,
                'score': score,
                'reasons': reasons
            })
    
    # Sort by score descending
    matches.sort(key=lambda x: -x['score'])
    
    return matches


def find_all_potential_matches(source_family, target_family, threshold=50):
    """
    Find all potential matches between two family trees.
    
    Args:
        source_family: The source FamilySpace
        target_family: The target FamilySpace
        threshold: Minimum score (0-100) to include
    
    Returns:
        List of match dictionaries with source_person, target_person, score, reasons
    """
    source_persons = Person.objects.filter(
        family=source_family,
        is_deleted=False
    )
    
    all_matches = []
    seen_pairs = set()
    
    for person in source_persons:
        matches = find_potential_matches(person, target_family, threshold)
        for match in matches:
            pair_key = tuple(sorted([person.id, match['person'].id]))
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                all_matches.append({
                    'source_person_id': person.id,
                    'source_person_name': person.full_name,
                    'target_person_id': match['person'].id,
                    'target_person_name': match['person'].full_name,
                    'score': match['score'],
                    'reasons': match['reasons']
                })
    
    # Sort by score descending
    all_matches.sort(key=lambda x: -x['score'])
    
    return all_matches


def create_person_link(person1, person2, proposed_by, score, reasons):
    """
    Create a CrossSpacePersonLink between two persons.
    
    Args:
        person1: First Person
        person2: Second Person  
        proposed_by: User proposing the link
        score: Match confidence score
        reasons: List of match reasons
    
    Returns:
        The created CrossSpacePersonLink
    """
    # Check if link already exists
    existing = CrossSpacePersonLink.objects.filter(
        Q(person1=person1, person2=person2) |
        Q(person1=person2, person2=person1)
    ).first()
    
    if existing:
        return existing
    
    link = CrossSpacePersonLink.objects.create(
        person1=person1,
        person2=person2,
        proposed_by=proposed_by,
        confidence_score=score,
        match_reasons=json.dumps(reasons)
    )
    
    return link
