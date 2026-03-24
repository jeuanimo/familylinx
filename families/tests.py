from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model

from .forms import GedcomUploadForm
from .models import FamilySpace, Person, Relationship
from .services.tree_builder import build_tree_json


class GedcomUploadFormTests(TestCase):
    def test_rejects_non_ged_file(self):
        bad_file = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        form = GedcomUploadForm(data={}, files={"gedcom_file": bad_file})
        self.assertFalse(form.is_valid())
        self.assertIn("valid GEDCOM file", form.errors["gedcom_file"][0])

    def test_accepts_ged_file(self):
        good_file = SimpleUploadedFile("family.ged", b"0 HEAD", content_type="text/plain")
        form = GedcomUploadForm(data={}, files={"gedcom_file": good_file})
        self.assertTrue(form.is_valid())


class TreeBuilderServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="u1", email="u1@example.com", password="pass")
        self.family = FamilySpace.objects.create(name="Test Family", created_by=self.user)
        self.parent = Person.objects.create(
            family=self.family, first_name="Parent", last_name="One", created_by=self.user
        )
        self.child = Person.objects.create(
            family=self.family, first_name="Child", last_name="One", created_by=self.user
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.parent,
            person2=self.child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

    def test_build_tree_json_returns_nodes_and_edges(self):
        data = build_tree_json(self.family)
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["edges"]), 1)
        edge = data["edges"][0]
        self.assertEqual(edge["type"], Relationship.Type.PARENT_CHILD)
