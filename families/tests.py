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
from .models import CrossSpacePersonLink, FamilyKudos, FamilySpace, FamilyMilestone, Invite, Membership, Person, Relationship
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


class FamilyTreeViewTests(TestCase):
    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_owner_can_open_tree_page_before_any_people_exist(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="emptytreeowner",
            email="emptytreeowner@example.com",
            password="pass",
        )
        family = FamilySpace.objects.create(name="Empty Tree Family", created_by=user)
        Membership.objects.create(
            family=family,
            user=user,
            role=Membership.Role.OWNER,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("families:family_tree", kwargs={"family_id": family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Family Tree")

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_interactive_tree_can_match_user_without_full_name_db_field(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="janedoe",
            email="janedoe@example.com",
            password="pass",
            first_name="Jane",
            last_name="Doe",
        )
        family = FamilySpace.objects.create(name="Interactive Tree Family", created_by=user)
        membership = Membership.objects.create(
            family=family,
            user=user,
            role=Membership.Role.OWNER,
        )
        person = Person.objects.create(
            family=family,
            first_name="Jane",
            last_name="Doe",
            created_by=user,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("families:family_tree_interactive", kwargs={"family_id": family.id}),
            secure=True,
        )

        membership.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(membership.linked_person, person)

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_interactive_tree_can_match_user_by_profile_maiden_name(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="janesmith",
            email="janesmith@example.com",
            password="pass",
            first_name="Jane",
            last_name="Doe",
        )
        user.profile.maiden_name = "Smith"
        user.profile.save(update_fields=["maiden_name"])
        family = FamilySpace.objects.create(name="Maiden Match Family", created_by=user)
        membership = Membership.objects.create(
            family=family,
            user=user,
            role=Membership.Role.OWNER,
        )
        person = Person.objects.create(
            family=family,
            first_name="Jane",
            last_name="Smith",
            created_by=user,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("families:family_tree_interactive", kwargs={"family_id": family.id}),
            secure=True,
        )

        membership.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(membership.linked_person, person)


class LinkToTreeViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="linkme",
            email="linkme@example.com",
            password="pass",
            first_name="Jane",
            last_name="Doe",
        )
        self.family = FamilySpace.objects.create(name="Link Family", created_by=self.user)
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.jane = Person.objects.create(
            family=self.family,
            first_name="Jane",
            last_name="Doe",
            maiden_name="Smith",
            birth_date=date(1988, 5, 12),
            created_by=self.user,
        )
        self.other = Person.objects.create(
            family=self.family,
            first_name="John",
            last_name="Johnson",
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_link_to_tree_renders_search_page_for_browser_requests(self):
        response = self.client.get(
            reverse("families:link_to_tree", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search by name")
        self.assertContains(response, "Link Yourself to the Family Tree")

    def test_link_to_tree_json_search_returns_matching_people(self):
        response = self.client.get(
            reverse("families:link_to_tree", kwargs={"family_id": self.family.id}),
            {"format": "json", "q": "Smith"},
            HTTP_ACCEPT="application/json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["linked_person_id"], None)
        self.assertEqual([person["id"] for person in payload["persons"]], [self.jane.id])
        self.assertEqual(payload["persons"][0]["maiden_name"], "Smith")

    def test_link_to_tree_form_post_links_membership(self):
        next_url = reverse("families:family_tree", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse("families:link_to_tree", kwargs={"family_id": self.family.id}),
            {"person_id": self.jane.id, "next": next_url},
            secure=True,
        )

        self.membership.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
        self.assertEqual(self.membership.linked_person, self.jane)


class ClaimMySpotMatchingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="middlematch",
            email="middlematch@example.com",
            password="pass",
            first_name="Jane",
            last_name="Doe",
        )
        self.user.profile.middle_name = "Marie"
        self.user.profile.save(update_fields=["middle_name"])
        self.family = FamilySpace.objects.create(name="GEDCOM Family", created_by=self.user)
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.person = Person.objects.create(
            family=self.family,
            first_name="Jane Marie",
            last_name="Doe",
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_claim_my_spot_suggests_person_with_middle_name_in_tree(self):
        response = self.client.get(
            reverse("families:claim_my_spot", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane Marie Doe")
        self.assertContains(response, self.person.full_name)

    def test_claim_my_spot_suggests_person_with_profile_maiden_name(self):
        self.user.profile.maiden_name = "Smith"
        self.user.profile.save(update_fields=["maiden_name"])
        maiden_person = Person.objects.create(
            family=self.family,
            first_name="Jane Marie",
            last_name="Smith",
            created_by=self.user,
        )

        response = self.client.get(
            reverse("families:claim_my_spot", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane Marie Doe (nee Smith)")
        self.assertContains(response, maiden_person.full_name)


class InviteEmailWorkflowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="inviteowner",
            email="inviteowner@example.com",
            password="pass",
        )
        self.family = FamilySpace.objects.create(name="Invite Family", created_by=self.user)
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.client.force_login(self.user)

    @patch("families.views.send_mail")
    def test_invite_create_email_contains_accept_url(self, mock_send_mail):
        response = self.client.post(
            reverse("families:invite_create", kwargs={"family_id": self.family.id}),
            {"email": "cousin@example.com", "role": Membership.Role.MEMBER},
            secure=True,
        )

        invite = Invite.objects.get(family=self.family, email="cousin@example.com")
        message = mock_send_mail.call_args.kwargs["message"]

        self.assertRedirects(
            response,
            reverse("families:family_detail", kwargs={"family_id": self.family.id}),
            fetch_redirect_response=False,
        )
        self.assertIn(
            reverse("families:invite_accept", kwargs={"token": invite.token}),
            message,
        )

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="contact@fam-linx.org",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="contact@fam-linx.org",
    )
    def test_invite_create_shows_reason_when_smtp_password_missing(self):
        response = self.client.post(
            reverse("families:invite_create", kwargs={"family_id": self.family.id}),
            {"email": "uncle@example.com", "role": Membership.Role.MEMBER},
            secure=True,
            follow=True,
        )

        invite = Invite.objects.get(family=self.family, email="uncle@example.com")

        self.assertContains(response, "EMAIL_HOST_PASSWORD")
        self.assertEqual(
            response.request["PATH_INFO"],
            reverse("families:family_detail", kwargs={"family_id": self.family.id}),
        )
        self.assertEqual(
            response.request["QUERY_STRING"],
            "",
        )
        self.assertIsNotNone(invite.last_email_attempt_at)
        self.assertIn("EMAIL_HOST_PASSWORD", invite.last_email_error)
        self.assertContains(response, "Email Failed")
        self.assertContains(response, "Email not sent.")
        self.assertContains(
            response,
            reverse("families:invite_accept", kwargs={"token": invite.token}),
        )


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
            birth_date=date(1975, milestone_day.month, milestone_day.day),
            created_by=self.user,
        )
        self.anniversary_relationship = Relationship.objects.create(
            family=self.family,
            person1=self.deceased_person,
            person2=self.spouse_person,
            relationship_type=Relationship.Type.SPOUSE,
            start_date=date(1990, milestone_day.month, milestone_day.day),
        )
        self.kudos = FamilyKudos.objects.create(
            family=self.family,
            title="College acceptance",
            message="We are celebrating a big achievement this week.",
            person=self.deceased_person,
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_family_detail_links_to_separate_family_date_pages(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})

        response = self.client.get(family_detail_url, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("families:birthday_list", kwargs={"family_id": self.family.id}),
        )
        self.assertContains(
            response,
            reverse("families:wedding_anniversary_list", kwargs={"family_id": self.family.id}),
        )
        self.assertContains(
            response,
            reverse("families:in_memoriam_list", kwargs={"family_id": self.family.id}),
        )
        self.assertContains(
            response,
            reverse("families:milestone_list", kwargs={"family_id": self.family.id}),
        )
        self.assertContains(
            response,
            reverse("families:kudos_list", kwargs={"family_id": self.family.id}),
        )

    def test_birthday_list_displays_people_with_edit_actions(self):
        person_edit_path = reverse(
            "families:person_edit",
            kwargs={"family_id": self.family.id, "person_id": self.spouse_person.id},
        )

        response = self.client.get(
            reverse("families:birthday_list", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Birthdays")
        self.assertContains(response, self.spouse_person.full_name)
        self.assertContains(response, person_edit_path)

    def test_in_memoriam_list_displays_people_with_edit_actions(self):
        person_edit_path = reverse(
            "families:person_edit",
            kwargs={"family_id": self.family.id, "person_id": self.deceased_person.id},
        )

        response = self.client.get(
            reverse("families:in_memoriam_list", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "In Memoriam")
        self.assertContains(response, self.deceased_person.full_name)
        self.assertContains(response, person_edit_path)

    def test_wedding_anniversary_list_displays_relationship_edit_actions(self):
        relationship_edit_path = reverse(
            "families:relationship_edit",
            kwargs={"family_id": self.family.id, "relationship_id": self.anniversary_relationship.id},
        )

        response = self.client.get(
            reverse("families:wedding_anniversary_list", kwargs={"family_id": self.family.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wedding Anniversaries")
        self.assertContains(response, self.deceased_person.full_name)
        self.assertContains(response, self.spouse_person.full_name)
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
        self.assertContains(response, "Custom Milestone Card")

    def test_kudos_detail_displays_saved_announcement(self):
        response = self.client.get(
            reverse(
                "families:kudos_detail",
                kwargs={"family_id": self.family.id, "kudos_id": self.kudos.id},
            ),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.kudos.title)
        self.assertContains(response, self.kudos.message)
        self.assertContains(response, "Announcement")

    def test_kudos_create_redirects_back_to_next_url(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse("families:kudos_create", kwargs={"family_id": self.family.id}),
            {
                "title": "New baby announcement",
                "message": "A beautiful new branch has arrived.",
                "person": self.spouse_person.id,
                "next": family_detail_url,
            },
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.assertTrue(
            FamilyKudos.objects.filter(family=self.family, title="New baby announcement").exists()
        )

    def test_kudos_edit_redirects_back_to_next_url(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse(
                "families:kudos_edit",
                kwargs={"family_id": self.family.id, "kudos_id": self.kudos.id},
            ),
            {
                "title": "Updated celebration",
                "message": "Updated announcement text",
                "person": self.spouse_person.id,
                "next": family_detail_url,
            },
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.kudos.refresh_from_db()
        self.assertEqual(self.kudos.title, "Updated celebration")

    def test_kudos_delete_redirects_back_to_next_url(self):
        family_detail_url = reverse("families:family_detail", kwargs={"family_id": self.family.id})
        response = self.client.post(
            reverse(
                "families:kudos_delete",
                kwargs={"family_id": self.family.id, "kudos_id": self.kudos.id},
            ),
            {"next": family_detail_url},
            secure=True,
        )

        self.assertRedirects(response, family_detail_url, fetch_redirect_response=False)
        self.assertFalse(
            FamilyKudos.objects.filter(id=self.kudos.id, family=self.family).exists()
        )

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
