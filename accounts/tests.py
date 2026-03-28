from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class UserProfileFormTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="profileuser",
            email="profileuser@example.com",
            password="pass",
        )
        self.client.force_login(self.user)

    def test_profile_edit_saves_first_middle_last_and_maiden_names(self):
        response = self.client.post(
            reverse("accounts:profile_edit"),
            {
                "first_name": "Jane",
                "middle_name": "Marie",
                "last_name": "Doe",
                "maiden_name": "Smith",
                "display_name": "",
                "bio": "",
                "location": "",
                "website": "",
                "date_of_birth": "",
                "profile_visibility": "MEMBERS",
                "show_birthday": "on",
            },
            secure=True,
        )

        self.user.refresh_from_db()
        profile = self.user.profile

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.first_name, "Jane")
        self.assertEqual(profile.middle_name, "Marie")
        self.assertEqual(self.user.last_name, "Doe")
        self.assertEqual(profile.maiden_name, "Smith")
        self.assertEqual(profile.get_full_name(), "Jane Marie Doe")
        self.assertEqual(profile.get_display_name(), "Jane Marie Doe")
