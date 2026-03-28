from unittest.mock import Mock, patch

import requests
from django.test import TestCase
from django.urls import reverse

from .views import FALLBACK_VERSE, VERSE_OF_THE_DAY_URL


class GodsWordOfDayViewTests(TestCase):
    @patch("config.views.requests.get")
    def test_page_uses_live_verse_when_api_succeeds(self, mock_get):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "verse": {
                "details": {
                    "text": "For with God nothing shall be impossible.",
                    "reference": "Luke 1:37",
                    "version": "KJV",
                }
            }
        }
        mock_get.return_value = mock_response

        response = self.client.get(reverse("gods_word_of_day"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "God's Word of the Day")
        self.assertContains(response, "For with God nothing shall be impossible.")
        self.assertContains(response, "Luke 1:37")
        self.assertContains(response, "KJV")
        self.assertContains(response, "Our Manna Verse of the Day API")
        self.assertFalse(response.context["is_fallback"])
        mock_get.assert_called_once_with(
            VERSE_OF_THE_DAY_URL,
            headers={"Accept": "application/json"},
            timeout=5,
        )

    @patch("config.views.requests.get", side_effect=requests.RequestException)
    def test_page_falls_back_when_api_fails(self, mock_get):
        response = self.client.get(reverse("gods_word_of_day"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, FALLBACK_VERSE["text"])
        self.assertContains(response, FALLBACK_VERSE["reference"])
        self.assertContains(response, "built-in scripture fallback")
        self.assertTrue(response.context["is_fallback"])
        mock_get.assert_called_once()
