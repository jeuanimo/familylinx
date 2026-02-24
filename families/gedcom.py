"""
GEDCOM Parser for FamilyLinx

Parses GEDCOM 5.5/5.5.1 files (the standard format from Ancestry, FamilySearch, etc.)
and imports person and relationship data into the family tree.

GEDCOM Format Overview:
- Line format: LEVEL [XREF_ID] TAG [VALUE]
- Level 0: Top-level records (HEAD, INDI, FAM, TRLR)
- INDI records: Individual persons
- FAM records: Family units (marriages/parent-child relationships)

Security Considerations:
- File size limits enforced before parsing
- Input sanitization on all text fields
- No execution of embedded content
"""

import re
from datetime import datetime
from django.utils.html import escape


class GedcomParseError(Exception):
    """Raised when GEDCOM parsing fails."""
    pass


class GedcomParser:
    """
    Parser for GEDCOM genealogy files.
    
    Implements Ancestry-style parsing:
    1. Entity Recognition: Extract INDI (individuals) and FAM (family) records
    2. Relationship Mapping: Use FAMC (child-to-family) and FAMS (spouse-to-family)
    3. Structure Translation: Transform to graph with nodes and relationship edges
    4. Data Normalization: Handle ABT, BEF, AFT date qualifiers
    5. Living Detection: Identify potentially living persons for privacy
    
    Usage:
        parser = GedcomParser()
        data = parser.parse(file_content)
        # data = {'individuals': [...], 'families': [...], 'living_count': int}
    """
    
    # Maximum file size (500MB - Ancestry limit)
    MAX_FILE_SIZE = 500 * 1024 * 1024
    
    # Threshold year - persons born after this without death date are likely living
    LIVING_THRESHOLD_YEAR = 1910
    
    def __init__(self):
        self.individuals = {}  # XREF_ID -> individual data
        self.families = {}     # XREF_ID -> family data
        self.current_record = None
        self.current_record_type = None
        self.current_xref = None
        self._current_event = None  # Track BIRT/DEAT/MARR events
        self._current_subtag = None  # Track level 1 tags
    
    def parse(self, content):
        """
        Parse GEDCOM content and return structured data.
        
        Args:
            content: String content of GEDCOM file
            
        Returns:
            dict with 'individuals' and 'families' lists
            
        Raises:
            GedcomParseError: If parsing fails
        """
        if len(content) > self.MAX_FILE_SIZE:
            raise GedcomParseError(f"File too large. Maximum size is {self.MAX_FILE_SIZE // 1024 // 1024}MB")
        
        lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                self._parse_line(line)
            except Exception as e:
                raise GedcomParseError(f"Error on line {line_num}: {str(e)}")
        
        # Finalize last record
        self._save_current_record()
        
        # Count living persons for privacy summary
        living_count = sum(1 for i in self.individuals.values() if i.get('is_likely_living'))
        
        return {
            'individuals': list(self.individuals.values()),
            'families': list(self.families.values()),
            'living_count': living_count,
            'total_count': len(self.individuals),
        }
    
    def _parse_line(self, line):
        """Parse a single GEDCOM line."""
        # GEDCOM line format: LEVEL [XREF_ID] TAG [VALUE]
        # Examples:
        #   0 @I1@ INDI
        #   1 NAME John /Smith/
        #   2 DATE 1 JAN 1900
        
        match = re.match(r'^(\d+)\s+(@[^@]+@)?\s*(\S+)\s*(.*)$', line)
        if not match:
            return  # Skip malformed lines
        
        level = int(match.group(1))
        xref = match.group(2)  # May be None
        tag = match.group(3).upper()
        value = match.group(4).strip() if match.group(4) else ''
        
        # Level 0 starts a new record
        if level == 0:
            self._save_current_record()
            
            if tag == 'INDI':
                self.current_record_type = 'INDI'
                self.current_xref = xref
                self.current_record = {
                    'xref': xref,
                    'first_name': '',
                    'last_name': '',
                    'maiden_name': '',
                    'gender': '',
                    'birth_date': None,
                    'birth_date_qualifier': '',  # ABT, BEF, AFT, EST
                    'birth_place': '',
                    'death_date': None,
                    'death_date_qualifier': '',  # ABT, BEF, AFT, EST
                    'death_place': '',
                    'fams': [],  # Families where this person is a spouse
                    'famc': None,  # Family where this person is a child
                    'is_likely_living': False,  # Privacy flag
                }
            elif tag == 'FAM':
                self.current_record_type = 'FAM'
                self.current_xref = xref
                self.current_record = {
                    'xref': xref,
                    'husb': None,  # Husband XREF
                    'wife': None,  # Wife XREF
                    'children': [],  # Child XREFs
                    'marriage_date': None,
                    'marriage_place': '',
                }
            else:
                self.current_record_type = None
                self.current_record = None
        
        # Process data within records
        elif self.current_record:
            if self.current_record_type == 'INDI':
                self._parse_individual_data(level, tag, value)
            elif self.current_record_type == 'FAM':
                self._parse_family_data(level, tag, value)
    
    def _parse_individual_data(self, level, tag, value):
        """Parse data tags within an INDI record."""
        if level == 1:
            self._current_subtag = tag
            # Reset current event when moving to a new level 1 tag
            # This prevents RESI, OCCU, etc. from overwriting BIRT/DEAT data
            self._current_event = None
            
            if tag == 'NAME':
                # Parse name: "First /Last/"
                name_match = re.match(r'^([^/]*)\s*/([^/]*)/?\s*(.*)$', value)
                if name_match:
                    self.current_record['first_name'] = escape(name_match.group(1).strip())
                    self.current_record['last_name'] = escape(name_match.group(2).strip())
                else:
                    # No surname delimiters, treat whole thing as first name
                    self.current_record['first_name'] = escape(value.strip())
            
            elif tag == 'SEX':
                if value.upper() == 'M':
                    self.current_record['gender'] = 'M'
                elif value.upper() == 'F':
                    self.current_record['gender'] = 'F'
                else:
                    self.current_record['gender'] = 'O'
            
            elif tag == 'FAMS':
                # Family as spouse
                self.current_record['fams'].append(value)
            
            elif tag == 'FAMC':
                # Family as child
                self.current_record['famc'] = value
            
            elif tag in ('BIRT', 'DEAT'):
                self._current_event = tag
        
        elif level == 2:
            if self._current_event == 'BIRT':
                if tag == 'DATE':
                    date_val, qualifier = self._parse_date_with_qualifier(value)
                    self.current_record['birth_date'] = date_val
                    self.current_record['birth_date_qualifier'] = qualifier
                elif tag == 'PLAC':
                    self.current_record['birth_place'] = escape(value[:200])
            
            elif self._current_event == 'DEAT':
                if tag == 'DATE':
                    date_val, qualifier = self._parse_date_with_qualifier(value)
                    self.current_record['death_date'] = date_val
                    self.current_record['death_date_qualifier'] = qualifier
                elif tag == 'PLAC':
                    self.current_record['death_place'] = escape(value[:200])
            
            # Maiden name (birth surname)
            if self._current_subtag == 'NAME' and tag == 'SURN':
                # Keep as maiden name if different from married name
                surname = escape(value.strip())
                if surname and surname != self.current_record['last_name']:
                    self.current_record['maiden_name'] = surname
    
    def _parse_family_data(self, level, tag, value):
        """Parse data tags within a FAM record."""
        if level == 1:
            self._current_subtag = tag
            
            if tag == 'HUSB':
                self.current_record['husb'] = value
            elif tag == 'WIFE':
                self.current_record['wife'] = value
            elif tag == 'CHIL':
                self.current_record['children'].append(value)
            elif tag == 'MARR':
                self._current_event = 'MARR'
        
        elif level == 2:
            if hasattr(self, '_current_event') and self._current_event == 'MARR':
                if tag == 'DATE':
                    self.current_record['marriage_date'] = self._parse_date(value)
                elif tag == 'PLAC':
                    self.current_record['marriage_place'] = escape(value[:200])
    
    def _parse_date(self, date_str):
        """
        Parse GEDCOM date string to Python date (strips qualifier).
        
        GEDCOM dates can be in various formats:
        - 1 JAN 1900
        - JAN 1900
        - 1900
        - ABT 1900 (approximate)
        - BEF 1900 (before)
        - AFT 1900 (after)
        """
        date_val, _ = self._parse_date_with_qualifier(date_str)
        return date_val
    
    def _parse_date_with_qualifier(self, date_str):
        """
        Parse GEDCOM date string, preserving the qualifier.
        
        Returns:
            tuple: (date or None, qualifier string)
            
        Qualifiers:
            - ABT: About/approximately
            - BEF: Before
            - AFT: After
            - EST: Estimated
            - CAL: Calculated
        """
        if not date_str:
            return None, ''
        
        date_str = date_str.upper().strip()
        qualifier = ''
        
        # Extract qualifier if present
        qualifier_match = re.match(r'^(ABT|BEF|AFT|EST|CAL|FROM|TO|BET)\s+', date_str)
        if qualifier_match:
            qualifier = qualifier_match.group(1)
            date_str = date_str[qualifier_match.end():]
        
        # Handle BET...AND ranges - take the first date
        if 'AND' in date_str:
            date_str = date_str.split('AND')[0].strip()
        
        # Month mapping
        months = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        
        # Try full date: "1 JAN 1900"
        match = re.match(r'^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$', date_str)
        if match:
            try:
                day = int(match.group(1))
                month = months.get(match.group(2), 1)
                year = int(match.group(3))
                return datetime(year, month, day).date(), qualifier
            except ValueError:
                pass
        
        # Try month/year: "JAN 1900"
        match = re.match(r'^([A-Z]{3})\s+(\d{4})$', date_str)
        if match:
            try:
                month = months.get(match.group(1), 1)
                year = int(match.group(2))
                return datetime(year, month, 1).date(), qualifier
            except ValueError:
                pass
        
        # Try year only: "1900"
        match = re.match(r'^(\d{4})$', date_str)
        if match:
            try:
                year = int(match.group(1))
                return datetime(year, 1, 1).date(), qualifier
            except ValueError:
                pass
        
        return None, qualifier
    
    def _save_current_record(self):
        """Save the current record to appropriate collection with living detection."""
        if not self.current_record or not self.current_xref:
            return
        
        if self.current_record_type == 'INDI':
            # Detect potentially living persons
            # A person is likely living if:
            # 1. No death date AND
            # 2. Born after threshold year OR no birth date
            birth_date = self.current_record.get('birth_date')
            death_date = self.current_record.get('death_date')
            
            if not death_date:
                if birth_date:
                    if birth_date.year > self.LIVING_THRESHOLD_YEAR:
                        self.current_record['is_likely_living'] = True
                else:
                    # No dates at all - assume possibly living
                    self.current_record['is_likely_living'] = True
            
            self.individuals[self.current_xref] = self.current_record
        elif self.current_record_type == 'FAM':
            self.families[self.current_xref] = self.current_record
        
        self.current_record = None
        self.current_record_type = None
        self.current_xref = None


def import_gedcom_to_family(gedcom_content, family, user):
    """
    Import GEDCOM data into a FamilySpace.
    
    Args:
        gedcom_content: String content of GEDCOM file
        family: FamilySpace instance to import into
        user: User performing the import
        
    Returns:
        dict with import statistics
    """
    from .models import Person, Relationship
    
    parser = GedcomParser()
    data = parser.parse(gedcom_content)
    
    # Track imported records
    xref_to_person = {}  # Maps GEDCOM XREF to Person instance
    stats = {
        'individuals_imported': 0,
        'relationships_created': 0,
        'errors': [],
    }
    
    # First pass: Create all Person records
    for indi in data['individuals']:
        try:
            # Skip if no name
            if not indi['first_name'] and not indi['last_name']:
                indi['first_name'] = 'Unknown'
            
            person = Person.objects.create(
                family=family,
                created_by=user,
                first_name=indi['first_name'] or 'Unknown',
                last_name=indi['last_name'] or '',
                maiden_name=indi['maiden_name'] or '',
                gender=indi['gender'] or 'O',
                birth_date=indi['birth_date'],
                birth_date_qualifier=indi.get('birth_date_qualifier', ''),
                birth_place=indi['birth_place'] or '',
                death_date=indi['death_date'],
                death_date_qualifier=indi.get('death_date_qualifier', ''),
                death_place=indi['death_place'] or '',
                is_private=indi.get('is_likely_living', False),
            )
            xref_to_person[indi['xref']] = person
            stats['individuals_imported'] += 1
        except Exception as e:
            stats['errors'].append(f"Error importing {indi.get('first_name', 'Unknown')}: {str(e)}")
    
    # Second pass: Create relationships from FAM records
    for fam in data['families']:
        husb_xref = fam.get('husb')
        wife_xref = fam.get('wife')
        children_xrefs = fam.get('children', [])
        
        husb = xref_to_person.get(husb_xref)
        wife = xref_to_person.get(wife_xref)
        
        # Create spouse relationship
        if husb and wife:
            try:
                # Check if relationship already exists
                existing = Relationship.objects.filter(
                    family=family,
                    person1=husb,
                    person2=wife,
                    relationship_type=Relationship.Type.SPOUSE
                ).exists() or Relationship.objects.filter(
                    family=family,
                    person1=wife,
                    person2=husb,
                    relationship_type=Relationship.Type.SPOUSE
                ).exists()
                
                if not existing:
                    Relationship.objects.create(
                        family=family,
                        person1=husb,
                        person2=wife,
                        relationship_type=Relationship.Type.SPOUSE,
                        start_date=fam.get('marriage_date'),
                    )
                    stats['relationships_created'] += 1
            except Exception as e:
                stats['errors'].append(f"Error creating spouse relationship: {str(e)}")
        
        # Create parent-child relationships
        for child_xref in children_xrefs:
            child = xref_to_person.get(child_xref)
            if not child:
                continue
            
            # Father-child relationship
            if husb:
                try:
                    existing = Relationship.objects.filter(
                        family=family,
                        person1=husb,
                        person2=child,
                        relationship_type=Relationship.Type.PARENT_CHILD
                    ).exists()
                    
                    if not existing:
                        Relationship.objects.create(
                            family=family,
                            person1=husb,
                            person2=child,
                            relationship_type=Relationship.Type.PARENT_CHILD,
                        )
                        stats['relationships_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Error creating father-child relationship: {str(e)}")
            
            # Mother-child relationship
            if wife:
                try:
                    existing = Relationship.objects.filter(
                        family=family,
                        person1=wife,
                        person2=child,
                        relationship_type=Relationship.Type.PARENT_CHILD
                    ).exists()
                    
                    if not existing:
                        Relationship.objects.create(
                            family=family,
                            person1=wife,
                            person2=child,
                            relationship_type=Relationship.Type.PARENT_CHILD,
                        )
                        stats['relationships_created'] += 1
                except Exception as e:
                    stats['errors'].append(f"Error creating mother-child relationship: {str(e)}")
    
    return stats


# =============================================================================
# Phase 7: Enhanced Import with Duplicate Detection
# =============================================================================

import json
from django.db.models import Q


def find_potential_duplicate(new_person_data, existing_persons):
    """
    Find potential duplicate person in existing records.
    
    Uses a scoring system based on:
    - Exact name match: +40 points
    - Similar name (Soundex/fuzzy): +20 points
    - Same birth year: +25 points
    - Same birth date: +35 points
    - Same birth place: +15 points
    - Same gender: +10 points
    
    Returns (existing_person, score, reasons) or (None, 0, [])
    """
    best_match = None
    best_score = 0
    best_reasons = []
    
    first_name = (new_person_data.get('first_name') or '').strip().lower()
    last_name = (new_person_data.get('last_name') or '').strip().lower()
    birth_date = new_person_data.get('birth_date')
    birth_place = (new_person_data.get('birth_place') or '').strip().lower()
    gender = new_person_data.get('gender')
    
    for person in existing_persons:
        score = 0
        reasons = []
        
        # Gender mismatch = definitely not the same person
        # Skip this person entirely if both have known but different genders
        if gender and person.gender and gender != person.gender:
            continue  # Cannot be a duplicate if genders differ
        
        existing_first = (person.first_name or '').strip().lower()
        existing_last = (person.last_name or '').strip().lower()
        
        # Name matching
        if first_name and last_name:
            if first_name == existing_first and last_name == existing_last:
                score += 40
                reasons.append("Exact name match")
            elif first_name == existing_first or last_name == existing_last:
                score += 20
                reasons.append("Partial name match")
            # Check maiden name
            existing_maiden = (person.maiden_name or '').strip().lower()
            if existing_maiden and last_name == existing_maiden:
                score += 15
                reasons.append("Last name matches maiden name")
        
        # Birth date matching
        if birth_date and person.birth_date:
            if birth_date == person.birth_date:
                score += 35
                reasons.append("Exact birth date match")
            elif birth_date.year == person.birth_date.year:
                score += 25
                reasons.append("Same birth year")
        
        # Birth place matching
        if birth_place and person.birth_place:
            existing_place = person.birth_place.strip().lower()
            if birth_place == existing_place:
                score += 15
                reasons.append("Same birth place")
            elif birth_place in existing_place or existing_place in birth_place:
                score += 10
                reasons.append("Similar birth place")
        
        # Gender matching
        if gender and person.gender and gender == person.gender:
            score += 10
            reasons.append("Same gender")
        
        # Update best match if this is higher
        if score > best_score and score >= 50:  # Minimum threshold
            best_score = score
            best_match = person
            best_reasons = reasons
    
    return best_match, best_score, best_reasons


def import_gedcom_with_tracking(gedcom_content, family, user, file_name, file_size=0):
    """
    Enhanced GEDCOM import with tracking and duplicate detection.
    
    Creates a GedcomImport record to track progress, detects potential
    duplicates during import, and creates PotentialDuplicate records
    for manual review.
    
    Args:
        gedcom_content: String content of GEDCOM file
        family: FamilySpace instance to import into
        user: User performing the import
        file_name: Original filename
        file_size: File size in bytes
        
    Returns:
        GedcomImport instance with all statistics
    """
    from .models import Person, Relationship, GedcomImport, PotentialDuplicate
    from django.utils import timezone
    
    # Create import record
    gedcom_import = GedcomImport.objects.create(
        family=family,
        uploaded_by=user,
        file_name=file_name,
        file_size=file_size,
        status=GedcomImport.Status.PROCESSING,
        started_at=timezone.now(),
    )
    
    errors = []
    
    try:
        parser = GedcomParser()
        data = parser.parse(gedcom_content)
        
        # Get existing persons for duplicate detection
        existing_persons = list(Person.objects.filter(family=family))
        
        # Track imported records
        xref_to_person = {}
        
        # First pass: Create Person records with duplicate detection
        for indi in data['individuals']:
            try:
                if not indi['first_name'] and not indi['last_name']:
                    indi['first_name'] = 'Unknown'
                
                # Check for duplicates
                duplicate_match, score, reasons = find_potential_duplicate(indi, existing_persons)
                
                # If 100% match (score >= 100), use existing person instead of creating new
                if duplicate_match and score >= 100:
                    xref_to_person[indi['xref']] = duplicate_match
                    gedcom_import.persons_updated += 1
                    continue
                
                # Create the new person
                person = Person.objects.create(
                    family=family,
                    created_by=user,
                    source_import=gedcom_import,
                    first_name=indi['first_name'] or 'Unknown',
                    last_name=indi['last_name'] or '',
                    maiden_name=indi['maiden_name'] or '',
                    gender=indi['gender'] or 'O',
                    birth_date=indi['birth_date'],
                    birth_date_qualifier=indi.get('birth_date_qualifier', ''),
                    birth_place=indi['birth_place'] or '',
                    death_date=indi['death_date'],
                    death_date_qualifier=indi.get('death_date_qualifier', ''),
                    death_place=indi['death_place'] or '',
                    is_private=indi.get('is_likely_living', False),
                )
                xref_to_person[indi['xref']] = person
                gedcom_import.persons_created += 1
                
                # If partial duplicate found (50-99%), create record for review
                if duplicate_match and score >= 50:
                    PotentialDuplicate.objects.create(
                        gedcom_import=gedcom_import,
                        existing_person=duplicate_match,
                        imported_person=person,
                        confidence_score=score,
                        match_reasons=json.dumps(reasons),
                    )
                    gedcom_import.duplicates_found += 1
                else:
                    # Add to existing persons for next duplicate checks
                    existing_persons.append(person)
                    
            except Exception as e:
                errors.append(f"Error importing {indi.get('first_name', 'Unknown')}: {str(e)}")
        
        # Second pass: Create relationships
        for fam in data['families']:
            husb_xref = fam.get('husb')
            wife_xref = fam.get('wife')
            children_xrefs = fam.get('children', [])
            
            husb = xref_to_person.get(husb_xref)
            wife = xref_to_person.get(wife_xref)
            
            # Create spouse relationship
            if husb and wife:
                try:
                    existing = Relationship.objects.filter(
                        family=family,
                        person1=husb,
                        person2=wife,
                        relationship_type=Relationship.Type.SPOUSE
                    ).exists() or Relationship.objects.filter(
                        family=family,
                        person1=wife,
                        person2=husb,
                        relationship_type=Relationship.Type.SPOUSE
                    ).exists()
                    
                    if not existing:
                        Relationship.objects.create(
                            family=family,
                            person1=husb,
                            person2=wife,
                            relationship_type=Relationship.Type.SPOUSE,
                            start_date=fam.get('marriage_date'),
                        )
                        gedcom_import.relationships_created += 1
                except Exception as e:
                    errors.append(f"Error creating spouse relationship: {str(e)}")
            
            # Create parent-child relationships
            for child_xref in children_xrefs:
                child = xref_to_person.get(child_xref)
                if not child:
                    continue
                
                if husb:
                    try:
                        existing = Relationship.objects.filter(
                            family=family,
                            person1=husb,
                            person2=child,
                            relationship_type=Relationship.Type.PARENT_CHILD
                        ).exists()
                        
                        if not existing:
                            Relationship.objects.create(
                                family=family,
                                person1=husb,
                                person2=child,
                                relationship_type=Relationship.Type.PARENT_CHILD,
                            )
                            gedcom_import.relationships_created += 1
                    except Exception as e:
                        errors.append(f"Error creating father-child relationship: {str(e)}")
                
                if wife:
                    try:
                        existing = Relationship.objects.filter(
                            family=family,
                            person1=wife,
                            person2=child,
                            relationship_type=Relationship.Type.PARENT_CHILD
                        ).exists()
                        
                        if not existing:
                            Relationship.objects.create(
                                family=family,
                                person1=wife,
                                person2=child,
                                relationship_type=Relationship.Type.PARENT_CHILD,
                            )
                            gedcom_import.relationships_created += 1
                    except Exception as e:
                        errors.append(f"Error creating mother-child relationship: {str(e)}")
        
        # Mark as completed
        gedcom_import.status = GedcomImport.Status.COMPLETED
        gedcom_import.completed_at = timezone.now()
        
    except GedcomParseError as e:
        gedcom_import.status = GedcomImport.Status.FAILED
        errors.append(f"Parse error: {str(e)}")
    except Exception as e:
        gedcom_import.status = GedcomImport.Status.FAILED
        errors.append(f"Unexpected error: {str(e)}")
    
    # Save errors and final state
    gedcom_import.errors = json.dumps(errors)
    gedcom_import.save()
    
    return gedcom_import


def merge_persons(keep_person, merge_person, reviewed_by=None):
    """
    Merge two Person records, keeping the first and deleting the second.
    
    Transfers all relationships from merge_person to keep_person,
    and optionally updates fields on keep_person with non-empty values
    from merge_person.
    
    Args:
        keep_person: Person to keep
        merge_person: Person to merge into keep_person and delete
        reviewed_by: User who performed the merge
        
    Returns:
        dict with merge statistics
    """
    from .models import Person, Relationship
    
    stats = {
        'relationships_transferred': 0,
        'fields_updated': [],
    }
    
    # Update missing fields on keep_person
    fields_to_check = [
        'maiden_name', 'birth_date', 'birth_place', 
        'death_date', 'death_place', 'bio'
    ]
    
    for field in fields_to_check:
        keep_value = getattr(keep_person, field)
        merge_value = getattr(merge_person, field)
        
        if not keep_value and merge_value:
            setattr(keep_person, field, merge_value)
            stats['fields_updated'].append(field)
    
    keep_person.save()
    
    # Transfer relationships from merge_person to keep_person
    # Update person1 references
    for rel in Relationship.objects.filter(person1=merge_person):
        if not Relationship.objects.filter(
            family=rel.family,
            person1=keep_person,
            person2=rel.person2,
            relationship_type=rel.relationship_type
        ).exists():
            rel.person1 = keep_person
            rel.save()
            stats['relationships_transferred'] += 1
        else:
            rel.delete()  # Duplicate relationship
    
    # Update person2 references
    for rel in Relationship.objects.filter(person2=merge_person):
        if not Relationship.objects.filter(
            family=rel.family,
            person1=rel.person1,
            person2=keep_person,
            relationship_type=rel.relationship_type
        ).exists():
            rel.person2 = keep_person
            rel.save()
            stats['relationships_transferred'] += 1
        else:
            rel.delete()  # Duplicate relationship
    
    # Transfer tagged photos
    for photo in merge_person.tagged_photos.all():
        if keep_person not in photo.tagged_people.all():
            photo.tagged_people.add(keep_person)
    
    # Delete the merge_person
    merge_person.delete()
    
    return stats
