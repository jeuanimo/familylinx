"""Utilities to convert family tree data into JSON for front-end renderers.

Separating this logic keeps views thin and makes it easy to reuse for
different visualizations (dTree now, D3 custom later).
"""

from typing import Dict, Any

from ..models import Person, Relationship, FamilySpace


def build_tree_json(family: FamilySpace, include_deleted: bool = False) -> Dict[str, Any]:
    """Return nodes/edges JSON for the given family.

    Args:
        family: FamilySpace instance to render.
        include_deleted: If True, include soft-deleted people/relationships.

    Returns:
        dict with `nodes` and `edges` lists ready for dTree/D3 consumption.
    """

    persons_qs = Person.objects.filter(family=family)
    relationships_qs = Relationship.objects.filter(family=family)

    if not include_deleted:
        persons_qs = persons_qs.filter(is_deleted=False)
        relationships_qs = relationships_qs.filter(is_deleted=False)

    nodes = [
        {
            "id": p.id,
            "name": p.full_name,
            "gender": p.gender,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
            "death_date": p.death_date.isoformat() if p.death_date else None,
            "is_living": p.is_living,
            "photo": p.photo.url if p.photo else None,
        }
        for p in persons_qs
    ]

    edges = [
        {
            "source": r.person1_id,
            "target": r.person2_id,
            "type": r.relationship_type,
        }
        for r in relationships_qs
    ]

    return {"nodes": nodes, "edges": edges}


__all__ = ["build_tree_json"]
