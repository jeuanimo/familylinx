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


class TempPerson:
    """Temporary person-like object for matching comparisons."""
    def __init__(self, first_name, last_name, birth_date=None, gender='U', maiden_name=''):
        self.first_name = first_name or ''
        self.last_name = last_name or ''
        self.maiden_name = maiden_name or ""
        self.birth_date = birth_date
        self.death_date = None
        self.birth_place = ""
        self.death_place = ""
        self.gender = gender or 'U'
        self.is_living = True


def names_share_given_name(name1, name2):
    """Return True when two given names clearly refer to the same name cluster."""
    normalized_1 = normalize_name(name1)
    normalized_2 = normalize_name(name2)
    if not (normalized_1 and normalized_2):
        return False

    if normalized_1 == normalized_2:
        return True
    if normalized_1.startswith(normalized_2 + " ") or normalized_2.startswith(normalized_1 + " "):
        return True

    parts_1 = normalized_1.split()
    parts_2 = normalized_2.split()
    return bool(parts_1 and parts_2 and parts_1[0] == parts_2[0])


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
        if names_share_given_name(fn1, fn2):
            fn_ratio = max(fn_ratio, 0.95)
        score += fn_ratio * 0.3
        if fn_ratio > 0.8:
            reasons.append(f"First names similar: {person1.first_name} ≈ {person2.first_name}")
    return score, reasons


def _compare_last_names(person1, person2, score, reasons):
    """Compare last names with Soundex bonus."""
    surname_pairs = []
    for surname1 in [person1.last_name, getattr(person1, "maiden_name", "")]:
        normalized_1 = normalize_name(surname1)
        if not normalized_1:
            continue
        for surname2 in [person2.last_name, getattr(person2, "maiden_name", "")]:
            normalized_2 = normalize_name(surname2)
            if normalized_2:
                surname_pairs.append((surname1, normalized_1, surname2, normalized_2))

    if not surname_pairs:
        return score, reasons

    display_1, ln1, display_2, ln2 = max(
        surname_pairs,
        key=lambda pair: SequenceMatcher(None, pair[1], pair[3]).ratio(),
    )
    ln_ratio = SequenceMatcher(None, ln1, ln2).ratio()
    score += ln_ratio * 0.4
    
    if ln_ratio > 0.8:
        reasons.append(f"Last names similar: {display_1} ≈ {display_2}")
    
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


def _filter_by_last_name(candidates, last_name):
    """Filter candidates by last name using Soundex and normalization."""
    if not last_name:
        return list(candidates)
    target_soundex = soundex(last_name)
    target_normalized = normalize_name(last_name)
    return [
        p for p in candidates 
        if soundex(p.last_name) == target_soundex or normalize_name(p.last_name) == target_normalized
    ]


def _add_first_name_matches(candidates, first_name, family, exclude_id=None):
    """Add persons matching by first name that weren't caught by last name filter."""
    if not first_name:
        return candidates
    
    fn_normalized = normalize_name(first_name)
    existing_ids = {p.id for p in candidates}
    
    additional = Person.objects.filter(family=family, is_deleted=False).exclude(id__in=existing_ids)
    if exclude_id:
        additional = additional.exclude(id=exclude_id)
    
    for p in additional:
        if normalize_name(p.first_name) == fn_normalized:
            candidates.append(p)
    
    return candidates


def _score_and_filter_matches(candidates, temp_person, threshold):
    """Score candidates and return those above threshold."""
    matches = []
    for candidate in candidates:
        score, reasons = calculate_match_score(temp_person, candidate)
        if score >= threshold:
            matches.append({'person': candidate, 'score': score, 'reasons': reasons})
    matches.sort(key=lambda x: -x['score'])
    return matches


def find_duplicates_in_family(first_name, last_name, family, birth_date=None, gender=None, exclude_id=None, threshold=40):
    """
    Find potential duplicate persons within the same family tree.
    
    Used when creating a new person to prevent duplicates.
    """
    candidates = Person.objects.filter(family=family, is_deleted=False)
    if exclude_id:
        candidates = candidates.exclude(id=exclude_id)
    
    candidates = _filter_by_last_name(candidates, last_name)
    candidates = _add_first_name_matches(candidates, first_name, family, exclude_id)
    
    temp = TempPerson(first_name, last_name, birth_date, gender)
    return _score_and_filter_matches(candidates, temp, threshold)


def _get_user_name_and_birthdate(user):
    """Extract first name, surname candidates, and birth date from a user."""
    profile = getattr(user, 'profile', None)
    first_name = user.first_name
    middle_name = getattr(profile, 'middle_name', '')
    last_name = user.last_name
    maiden_name = getattr(profile, 'maiden_name', '')

    if middle_name:
        first_name = " ".join(part for part in [first_name, middle_name] if part)
    
    # Try to parse display name if first_name is missing
    if not first_name and profile and profile.display_name:
        parts = profile.display_name.strip().split()
        if parts:
            first_name = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]
            if len(parts) > 1:
                last_name = parts[-1]
    
    birth_date = profile.date_of_birth if profile else None
    last_names = []
    for value in [last_name, maiden_name]:
        normalized = normalize_name(value)
        if normalized and normalized not in last_names:
            last_names.append(normalized)
    return first_name, last_names, birth_date


def _filter_unlinked_by_name(candidates, first_name, last_names):
    """Filter unlinked persons by name similarity (first or last name match)."""
    fn_normalized = normalize_name(first_name) if first_name else ""
    normalized_last_names = [normalize_name(last_name) for last_name in last_names if last_name]
    
    filtered = []
    for person in candidates:
        person_fn = normalize_name(person.first_name)
        person_last_names = [
            normalize_name(person.last_name),
            normalize_name(person.maiden_name),
        ]
        
        fn_match = fn_normalized and names_share_given_name(fn_normalized, person_fn)
        ln_match = any(
            user_last and person_last and (
                user_last == person_last or soundex(user_last) == soundex(person_last)
            )
            for user_last in normalized_last_names
            for person_last in person_last_names
        )
        
        if fn_match or ln_match:
            filtered.append(person)
    
    return filtered


def find_member_on_tree(user, family, threshold=35):
    """
    Find potential matches for a user on the family tree.
    
    Used when a new member joins to suggest if they already exist on the tree.
    """
    first_name, last_names, birth_date = _get_user_name_and_birthdate(user)
    
    if not (first_name or last_names):
        return []
    
    candidates = Person.objects.filter(
        family=family,
        is_deleted=False,
        linked_user__isnull=True
    )
    
    filtered = _filter_unlinked_by_name(candidates, first_name, last_names)

    current_last_name = user.last_name
    maiden_name = getattr(getattr(user, 'profile', None), 'maiden_name', '')
    temp = TempPerson(first_name, current_last_name, birth_date, maiden_name=maiden_name)
    return _score_and_filter_matches(filtered, temp, threshold)
