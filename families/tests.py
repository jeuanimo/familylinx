import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .forms import GedcomUploadForm
from .models import CrossSpacePersonLink, FamilySpace, FamilyMilestone, Membership, Person, Relationship
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


class FamilyMilestoneWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="milestones", email="milestones@example.com", password="pass")
        self.family = FamilySpace.objects.create(name="Milestone Family", created_by=self.user)
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.MEMBER,
        )
        self.milestone = FamilyMilestone.objects.create(
            family=self.family,
            title="Family reunion",
            description="Everyone is coming together this spring.",
            date=timezone.localdate() + timedelta(days=7),
            created_by=self.user,
        )
        milestone_day = timezone.localdate() + timedelta(days=5)
        self.deceased_person = Person.objects.create(
            family=self.family,
            first_name="Mary",
            last_name="Ancestor",
            gender=Person.Gender.FEMALE,
            death_date=date(2001, milestone_day.month, milestone_day.day),
            death_place="Springfield",
            created_by=self.user,
        )
        self.spouse_person = Person.objects.create(
            family=self.family,
            first_name="John",
            last_name="Ancestor",
            gender=Person.Gender.MALE,
            created_by=self.user,
        )
        self.anniversary_relationship = Relationship.objects.create(
            family=self.family,
            person1=self.deceased_person,
            person2=self.spouse_person,
            relationship_type=Relationship.Type.SPOUSE,
            start_date=date(1990, milestone_day.month, milestone_day.day),
        )
        self.client.force_login(self.user)

    def test_family_detail_custom_milestone_card_links_back_to_current_page(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        edit_path = reverse(
            "families:milestone_edit",
            kwargs={"family_id": self.family.id, "milestone_id": self.milestone.id},
        )
        delete_path = reverse(
            "families:milestone_delete",
            kwargs={"family_id": self.family.id, "milestone_id": self.milestone.id},
        )
        detail_path = reverse(
            "families:milestone_detail",
            kwargs={"family_id": self.family.id, "milestone_id": self.milestone.id},
        )

        response = self.client.get(family_detail_url, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, detail_path)
        self.assertContains(response, edit_path)
        self.assertContains(response, delete_path)
        self.assertContains(response, "next=")

    def test_family_detail_imported_milestone_cards_offer_edit_actions(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        person_edit_path = reverse(
            "families:person_edit",
            kwargs={"family_id": self.family.id, "person_id": self.deceased_person.id},
        )
        relationship_edit_path = reverse(
            "families:relationship_edit",
            kwargs={"family_id": self.family.id, "relationship_id": self.anniversary_relationship.id},
        )

        response = self.client.get(family_detail_url, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Person")
        self.assertContains(response, "Edit Relationship")
        self.assertContains(response, person_edit_path)
        self.assertContains(response, relationship_edit_path)

    def test_milestone_detail_displays_saved_card(self):
        response = self.client.get(
            reverse(
                "families:milestone_detail",
                kwargs={"family_id": self.family.id, "milestone_id": self.milestone.id},
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.milestone.title)
        self.assertContains(response, self.milestone.description)
        self.assertContains(response, "Milestone Card")

    def test_milestone_create_redirects_back_to_next_url(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse("families:milestone_create", kwargs={"family_id": self.family.id}),
            {
                "title": "Graduation day",
                "description": "A new chapter starts.",
                "date": (timezone.localdate() + timedelta(days=12)).isoformat(),
                "person": "",
                "event": "",
                "next": family_detail_url,
            },
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.assertTrue(
            FamilyMilestone.objects.filter(family=self.family, title="Graduation day").exists()
        )

    def test_milestone_edit_redirects_back_to_next_url(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse(
                "families:milestone_edit",
                kwargs={"family_id": self.family.id, "milestone_id": self.milestone.id},
            ),
            {
                "title": "Updated reunion",
                "description": "Updated description",
                "date": (timezone.localdate() + timedelta(days=10)).isoformat(),
                "person": "",
                "event": "",
                "next": family_detail_url,
            },
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.milestone.refresh_from_db()
        self.assertEqual(self.milestone.title, "Updated reunion")

    def test_milestone_delete_redirects_back_to_next_url(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse(
                "families:milestone_delete",
                kwargs={"family_id": self.family.id, "milestone_id": self.milestone.id},
            ),
            {"next": family_detail_url},
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.assertFalse(
            FamilyMilestone.objects.filter(id=self.milestone.id, family=self.family).exists()
        )

    def test_person_edit_from_imported_milestone_redirects_back_to_family_page(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse(
                "families:person_edit",
                kwargs={"family_id": self.family.id, "person_id": self.deceased_person.id},
            ),
            {
                "first_name": "Mary",
                "last_name": "Ancestor",
                "maiden_name": "",
                "gender": Person.Gender.FEMALE,
                "birth_date": "",
                "death_date": self.deceased_person.death_date.isoformat(),
                "birth_place": "",
                "death_place": "Updated memorial location",
                "bio": "Updated after the GEDCOM import.",
                "father": "",
                "mother": "",
                "spouse": self.spouse_person.id,
                "other_parent": "",
                "next": family_detail_url,
            },
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.deceased_person.refresh_from_db()
        self.assertEqual(self.deceased_person.death_place, "Updated memorial location")
        self.assertEqual(self.deceased_person.bio, "Updated after the GEDCOM import.")

    def test_relationship_edit_from_imported_milestone_redirects_back_to_family_page(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        updated_date = timezone.localdate() + timedelta(days=8)
        response = self.client.post(
            reverse(
                "families:relationship_edit",
                kwargs={"family_id": self.family.id, "relationship_id": self.anniversary_relationship.id},
            ),
            {
                "person2": self.spouse_person.id,
                "relationship_type": Relationship.Type.SPOUSE,
                "start_date": date(1990, updated_date.month, updated_date.day).isoformat(),
                "end_date": "",
                "notes": "Updated anniversary date after import cleanup.",
                "next": family_detail_url,
            },
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.anniversary_relationship.refresh_from_db()
        self.assertEqual(
            self.anniversary_relationship.start_date,
            date(1990, updated_date.month, updated_date.day),
        )
        self.assertEqual(
            self.anniversary_relationship.notes,
            "Updated anniversary date after import cleanup.",
        )


class FamilyLineSpaceCreationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="branchbuilder",
            email="branchbuilder@example.com",
            password="pass",
        )
        self.family = FamilySpace.objects.create(
            name="Heritage Roots",
            created_by=self.user,
        )
        self.focal_person = Person.objects.create(
            family=self.family,
            first_name="Alice",
            last_name="Branch",
            gender=Person.Gender.FEMALE,
            created_by=self.user,
            linked_user=self.user,
        )
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.ADMIN,
            linked_person=self.focal_person,
        )
        self.mother = Person.objects.create(
            family=self.family,
            first_name="Maria",
            last_name="Branch",
            gender=Person.Gender.FEMALE,
            created_by=self.user,
        )
        self.father = Person.objects.create(
            family=self.family,
            first_name="Peter",
            last_name="Branch",
            gender=Person.Gender.MALE,
            created_by=self.user,
        )
        self.child = Person.objects.create(
            family=self.family,
            first_name="Sophie",
            last_name="Branch",
            gender=Person.Gender.FEMALE,
            created_by=self.user,
        )
        self.spouse = Person.objects.create(
            family=self.family,
            first_name="Daniel",
            last_name="Branch",
            gender=Person.Gender.MALE,
            created_by=self.user,
        )
        self.spouse_mother = Person.objects.create(
            family=self.family,
            first_name="Helen",
            last_name="Branch",
            gender=Person.Gender.FEMALE,
            created_by=self.user,
        )
        self.spouse_other_parent = Person.objects.create(
            family=self.family,
            first_name="Rachel",
            last_name="Branch",
            gender=Person.Gender.FEMALE,
            created_by=self.user,
        )
        self.spouse_only_child = Person.objects.create(
            family=self.family,
            first_name="Ethan",
            last_name="Branch",
            gender=Person.Gender.MALE,
            created_by=self.user,
        )

        Relationship.objects.create(
            family=self.family,
            person1=self.mother,
            person2=self.focal_person,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.father,
            person2=self.focal_person,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.focal_person,
            person2=self.child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.focal_person,
            person2=self.spouse,
            relationship_type=Relationship.Type.SPOUSE,
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.spouse_mother,
            person2=self.spouse,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.spouse,
            person2=self.spouse_only_child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )
        Relationship.objects.create(
            family=self.family,
            person1=self.spouse_other_parent,
            person2=self.spouse_only_child,
            relationship_type=Relationship.Type.PARENT_CHILD,
        )

        self.client.force_login(self.user)

    def test_family_tree_page_shows_branch_space_creator_for_editors(self):
        response = self.client.get(
            reverse("families:family_tree", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Branch Space")
        self.assertContains(response, 'id="lineSpaceName"', html=False)
        self.assertContains(response, 'id="linePersonSide"', html=False)
        self.assertContains(response, 'id="lineSpouseSide"', html=False)
        self.assertContains(response, 'id="lineSpouseId"', html=False)

    def test_family_line_create_space_api_creates_separate_family_space(self):
        response = self.client.post(
            reverse("families_api:family_line_create_space", kwargs={"family_id": self.family.id}),
            data=json.dumps({
                "name": "Heritage Roots - Maternal Branch",
                "person_id": self.focal_person.id,
                "line": "maternal",
                "mode": "subtree",
                "include_spouses": True,
            }),
            content_type="application/json",
            secure=True,
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()

        new_family = FamilySpace.objects.get(id=payload["new_family_id"])
        self.assertEqual(new_family.name, "Heritage Roots - Maternal Branch")
        self.assertEqual(
            payload["new_family_url"],
            reverse("families:family_detail", kwargs={"family_id": new_family.id}),
        )

        new_membership = Membership.objects.get(family=new_family, user=self.user)
        self.assertEqual(new_membership.role, Membership.Role.OWNER)
        self.assertIsNotNone(new_membership.linked_person)
        self.assertEqual(new_membership.linked_person.first_name, "Alice")
        self.assertIsNone(new_membership.linked_person.linked_user)

        copied_names = set(
            Person.objects.filter(family=new_family).values_list("first_name", flat=True)
        )
        self.assertTrue({"Alice", "Maria", "Sophie", "Daniel"}.issubset(copied_names))
        self.assertNotIn("Peter", copied_names)
        self.assertNotIn("Ethan", copied_names)

    def test_family_line_create_space_api_creates_spouse_side_space(self):
        response = self.client.post(
            reverse("families_api:family_line_create_space", kwargs={"family_id": self.family.id}),
            data=json.dumps({
                "name": "Heritage Roots - Husband Side",
                "person_id": self.focal_person.id,
                "line": "spouse_side",
                "spouse_id": self.spouse.id,
                "mode": "subtree",
                "include_spouses": True,
            }),
            content_type="application/json",
            secure=True,
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()

        new_family = FamilySpace.objects.get(id=payload["new_family_id"])
        copied_names = set(
            Person.objects.filter(family=new_family).values_list("first_name", flat=True)
        )

        self.assertEqual(new_family.name, "Heritage Roots - Husband Side")
        self.assertTrue({"Daniel", "Helen", "Alice", "Sophie", "Ethan"}.issubset(copied_names))
        self.assertNotIn("Maria", copied_names)
        self.assertNotIn("Peter", copied_names)


class CrossFamilySyncReviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="syncer",
            email="syncer@example.com",
            password="pass",
        )
        self.local_family = FamilySpace.objects.create(
            name="Maternal Space",
            created_by=self.user,
        )
        self.remote_family = FamilySpace.objects.create(
            name="Paternal Space",
            created_by=self.user,
        )
        Membership.objects.create(
            family=self.local_family,
            user=self.user,
            role=Membership.Role.ADMIN,
        )
        Membership.objects.create(
            family=self.remote_family,
            user=self.user,
            role=Membership.Role.ADMIN,
        )

        self.local_person = Person.objects.create(
            family=self.local_family,
            first_name="Mary",
            last_name="Walker",
            gender=Person.Gender.FEMALE,
            birth_place="",
            death_place="",
            bio="Original local biography.",
            created_by=self.user,
        )
        self.remote_person = Person.objects.create(
            family=self.remote_family,
            first_name="Mary",
            last_name="Walker",
            gender=Person.Gender.FEMALE,
            birth_place="Springfield, Illinois",
            death_place="Tulsa, Oklahoma",
            bio="Updated biography from the other branch.",
            created_by=self.user,
        )
        self.link = CrossSpacePersonLink.objects.create(
            person1=self.local_person,
            person2=self.remote_person,
            proposed_by=self.user,
            status=CrossSpacePersonLink.Status.CONFIRMED,
            confidence_score=92,
            confirmed_by_space1=True,
            confirmed_by_space2=True,
        )
        self.client.force_login(self.user)

    def test_confirmed_links_page_exposes_review_changes_action(self):
        response = self.client.get(
            reverse("families:tree_link_list", kwargs={"family_id": self.local_family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "families:tree_link_review",
                kwargs={"family_id": self.local_family.id, "link_id": self.link.id},
            ),
        )
        self.assertContains(response, "3 fields differ")

    def test_tree_link_review_applies_only_selected_fields_to_current_family_person(self):
        review_url = reverse(
            "families:tree_link_review",
            kwargs={"family_id": self.local_family.id, "link_id": self.link.id},
        )

        response = self.client.post(
            review_url,
            {"fields": ["death_place", "bio"]},
            secure=True,
        )

        self.assertRedirects(response, review_url, fetch_redirect_response=False)
        self.local_person.refresh_from_db()
        self.remote_person.refresh_from_db()

        self.assertEqual(self.local_person.death_place, "Tulsa, Oklahoma")
        self.assertEqual(self.local_person.bio, "Updated biography from the other branch.")
        self.assertEqual(self.local_person.birth_place, "")
        self.assertEqual(self.remote_person.birth_place, "Springfield, Illinois")

    def test_tree_link_review_page_lists_field_differences(self):
        response = self.client.get(
            reverse(
                "families:tree_link_review",
                kwargs={"family_id": self.local_family.id, "link_id": self.link.id},
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Field Differences (3)")
        self.assertContains(response, "Birth place")
        self.assertContains(response, "Death place")
        self.assertContains(response, "Biography")


class PrepareDeploymentDataCommandTests(TestCase):
    def test_command_writes_fixture_and_media_manifest(self):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        media_root = Path(temp_dir.name) / "media"
        media_root.mkdir(parents=True, exist_ok=True)
        avatar_path = media_root / "profiles" / "avatars" / "seed.jpg"
        avatar_path.parent.mkdir(parents=True, exist_ok=True)
        avatar_path.write_bytes(b"fake-image-bytes")

        output_dir = Path(temp_dir.name) / "exports"

        with override_settings(MEDIA_ROOT=media_root):
            User = get_user_model()
            user = User.objects.create_user(
                username="deployprep",
                email="deployprep@example.com",
                password="pass",
            )
            family = FamilySpace.objects.create(name="Deploy Family", created_by=user)
            Membership.objects.create(family=family, user=user, role=Membership.Role.OWNER)
            profile = user.profile
            profile.profile_picture.name = "profiles/avatars/seed.jpg"
            profile.save(update_fields=["profile_picture"])

            with patch("families.management.commands.prepare_deployment_data.timezone.now") as mock_now:
                mock_now.return_value.isoformat.return_value = "2026-03-28T04:00:00+00:00"
                call_command("prepare_deployment_data", output_dir=str(output_dir))

        fixture_path = output_dir / "render_seed.json"
        manifest_path = output_dir / "media_manifest.json"

        self.assertTrue(fixture_path.exists())
        self.assertTrue(manifest_path.exists())

        fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertTrue(any(item["model"] == "families.familyspace" for item in fixture_data))

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_data["generated_at"], "2026-03-28T04:00:00+00:00")
        self.assertEqual(manifest_data["file_count"], 1)
        self.assertEqual(manifest_data["missing_count"], 0)
        self.assertEqual(manifest_data["files"][0]["field"], "profile_picture")
        self.assertTrue(manifest_data["files"][0]["exists"])
