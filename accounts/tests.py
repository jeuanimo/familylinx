from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from django.urls import reverse

from families.models import FamilySpace, Membership


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


class AuthPortalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="portaluser",
            email="portaluser@example.com",
            password="StrongPass123!",
        )

    def test_auth_portal_renders_both_forms(self):
        response = self.client.get(reverse("accounts:auth_portal"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Access FamilyLinx")
        self.assertContains(response, "Sign In")
        self.assertContains(response, "Create Account")

    def test_auth_portal_logs_user_in_and_redirects_to_next(self):
        target = reverse("home")
        response = self.client.post(
            reverse("accounts:auth_portal"),
            {
                "auth_action": "login",
                "login": "portaluser",
                "password": "StrongPass123!",
                "next": target,
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)


class SecurityBlockerMiddlewareTests(TestCase):
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_blocks_known_exploit_paths(self):
        response = self.client.get(
            "/vendor/phpunit/eval-stdin.php",
            secure=True,
            REMOTE_ADDR="203.0.113.9",
            HTTP_USER_AGENT="Mozilla/5.0",
        )

        self.assertEqual(response.status_code, 403)

    def test_blocks_known_scanner_user_agents(self):
        response = self.client.get(
            "/",
            secure=True,
            REMOTE_ADDR="203.0.113.10",
            HTTP_USER_AGENT="Mozilla/5.0 nuclei",
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(
        SECURITY_BLOCKER_RATE_LIMIT_WINDOW_SECONDS=60,
        SECURITY_BLOCKER_MAX_REQUESTS_PER_WINDOW=2,
        SECURITY_BLOCKER_RATE_LIMIT_AUTHENTICATED=False,
    )
    def test_rate_limits_repeated_requests_from_same_ip(self):
        for _ in range(2):
            response = self.client.get(
                "/",
                secure=True,
                REMOTE_ADDR="198.51.100.8",
                HTTP_USER_AGENT="Mozilla/5.0",
            )
            self.assertEqual(response.status_code, 200)

        blocked = self.client.get(
            "/",
            secure=True,
            REMOTE_ADDR="198.51.100.8",
            HTTP_USER_AGENT="Mozilla/5.0",
        )

        self.assertEqual(blocked.status_code, 429)

    def test_blocked_requests_are_logged_with_reason(self):
        with self.assertLogs("familylinx.security.blocker", level="WARNING") as captured:
            response = self.client.get(
                "/?payload=%3Cscript%3E",
                secure=True,
                HTTP_X_FORWARDED_FOR="198.51.100.44, 10.0.0.1",
                HTTP_USER_AGENT="Mozilla/5.0",
            )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(any("reason=blocked_query_signature" in message for message in captured.output))
        self.assertTrue(any("ip=198.51.100.44" in message for message in captured.output))


class UserDirectoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(
            username="viewer",
            email="viewer@example.com",
            password="pass",
            first_name="View",
            last_name="User",
        )
        self.visible_user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="pass",
            first_name="Alice",
            last_name="Walker",
        )
        self.hidden_user = User.objects.create_user(
            username="ghost",
            email="ghost@example.com",
            password="pass",
        )

        now = timezone.now()
        User.objects.filter(id=self.viewer.id).update(last_login=now)
        User.objects.filter(id=self.visible_user.id).update(last_login=now)

        self.viewer.refresh_from_db()
        self.visible_user.refresh_from_db()
        self.hidden_user.refresh_from_db()

        self.visible_user.profile.display_name = "Alice Walker"
        self.visible_user.profile.save(update_fields=["display_name"])

        self.client.force_login(self.viewer)

    def test_user_directory_lists_only_users_who_have_logged_in(self):
        response = self.client.get(reverse("accounts:user_directory"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Walker")
        self.assertContains(response, "viewer@example.com")
        self.assertNotContains(response, "ghost@example.com")

    def test_user_directory_search_filters_results(self):
        response = self.client.get(reverse("accounts:user_directory"), {"q": "alice"}, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Walker")
        self.assertNotContains(response, "viewer@example.com")


class ProfileVisibilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.viewer = User.objects.create_user(
            username="viewer2",
            email="viewer2@example.com",
            password="pass",
        )
        self.other_user = User.objects.create_user(
            username="membersonly",
            email="membersonly@example.com",
            password="pass",
        )
        self.client.force_login(self.viewer)

    def test_members_only_profile_is_blocked_without_shared_family(self):
        profile = self.other_user.profile
        profile.profile_visibility = "MEMBERS"
        profile.display_name = "Members Only User"
        profile.save(update_fields=["profile_visibility", "display_name"])

        response = self.client.get(
            reverse("accounts:profile_view", kwargs={"user_id": self.other_user.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Family Members Only")
        self.assertContains(response, "share a family space")

    def test_members_only_profile_is_visible_with_shared_family(self):
        family = FamilySpace.objects.create(name="Shared Space", created_by=self.viewer)
        Membership.objects.create(family=family, user=self.viewer, role=Membership.Role.OWNER)
        Membership.objects.create(family=family, user=self.other_user, role=Membership.Role.MEMBER)

        profile = self.other_user.profile
        profile.profile_visibility = "MEMBERS"
        profile.display_name = "Shared Family User"
        profile.save(update_fields=["profile_visibility", "display_name"])

        response = self.client.get(
            reverse("accounts:profile_view", kwargs={"user_id": self.other_user.id}),
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shared Family User")
        self.assertNotContains(response, "Family Members Only")


class AdminUserDirectoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="staffer",
            email="staffer@example.com",
            password="pass",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="pass",
            first_name="Regular",
            last_name="User",
        )
        self.new_user = User.objects.create_user(
            username="neverlogged",
            email="neverlogged@example.com",
            password="pass",
        )
        now = timezone.now()
        User.objects.filter(id=self.staff_user.id).update(last_login=now)
        User.objects.filter(id=self.regular_user.id).update(last_login=now)
        self.staff_user.refresh_from_db()
        self.regular_user.refresh_from_db()
        self.new_user.refresh_from_db()

    def test_admin_directory_requires_staff_access(self):
        self.client.force_login(self.regular_user)

        response = self.client.get(reverse("accounts:admin_user_directory"), secure=True)

        self.assertEqual(response.status_code, 403)

    def test_admin_directory_lists_all_accounts_and_statuses(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("accounts:admin_user_directory"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "staffer@example.com")
        self.assertContains(response, "regular@example.com")
        self.assertContains(response, "neverlogged@example.com")
        self.assertContains(response, "Never Logged In")
        self.assertContains(response, "Total accounts")

    def test_admin_directory_search_filters_accounts(self):
        self.client.force_login(self.staff_user)

        response = self.client.get(
            reverse("accounts:admin_user_directory"),
            {"q": "neverlogged"},
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "neverlogged@example.com")
        self.assertNotContains(response, "regular@example.com")
