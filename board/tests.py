import shutil
import tempfile
from django.test import SimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from unittest.mock import MagicMock, patch

from board.forms import LoginForm
from board.models import Post, SoccerMatch
from board.templatetags.board_extras import render_post_content
from board.views import _format_accuracy_rate, _match_bet_accuracy_stats, _match_bet_accuracy_stats_by_league


class SsulPostApiTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp()
        cls._override_settings = override_settings(ALLOWED_HOSTS=["testserver"], MEDIA_ROOT=cls._media_root)
        cls._override_settings.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override_settings.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.client = Client()

    def _image(self, name):
        return SimpleUploadedFile(name, b"image-content", content_type="image/jpeg")

    def test_ssul_list_returns_common_posts_only(self):
        common_post = Post.objects.create(title="썰 제목", content="썰 내용", category="common")
        Post.objects.create(title="비밀 제목", content="비밀 내용", category="secret")

        response = self.client.get("/api/v1/ssul-posts/")

        self.assertEqual(response.status_code, 200)
        post_ids = [post["id"] for post in response.json()["results"]]
        self.assertEqual(post_ids, [common_post.id])

    def test_ssul_detail_returns_post_and_increments_views(self):
        post = Post.objects.create(title="읽을 글", content="본문", category="common")

        response = self.client.get(f"/api/v1/ssul-posts/{post.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["post"]["id"], post.id)
        post.refresh_from_db()
        self.assertEqual(post.views, 1)

    def test_ssul_detail_does_not_expose_secret_posts(self):
        post = Post.objects.create(title="비밀 글", content="본문", category="secret")

        response = self.client.get(f"/api/v1/ssul-posts/{post.id}/")

        self.assertEqual(response.status_code, 404)

    def test_ssul_create_accepts_up_to_three_images(self):
        response = self.client.post(
            "/api/v1/ssul-posts/",
            {
                "title": "사진 글",
                "content": "사진 본문",
                "category": "secret",
                "images": [self._image("one.jpg"), self._image("two.jpg"), self._image("three.jpg")],
            },
        )

        self.assertEqual(response.status_code, 201)
        post = Post.objects.get()
        self.assertEqual(post.category, "common")
        self.assertEqual(post.images.count(), 3)
        self.assertEqual(len(response.json()["post"]["images"]), 3)

    def test_ssul_create_rejects_more_than_three_images(self):
        response = self.client.post(
            "/api/v1/ssul-posts/",
            {
                "title": "사진 글",
                "content": "사진 본문",
                "images": [
                    self._image("one.jpg"),
                    self._image("two.jpg"),
                    self._image("three.jpg"),
                    self._image("four.jpg"),
                ],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)
        self.assertIn("images", response.json()["errors"])


class RenderPostContentTests(SimpleTestCase):
    def test_renders_plain_link(self):
        rendered = render_post_content("일반 링크 https://example.com")

        self.assertIn('href="https://example.com"', rendered)
        self.assertNotIn("youtube.com/embed/", rendered)

    def test_embeds_youtube_watch_url(self):
        rendered = render_post_content("영상 https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        self.assertIn("https://www.youtube.com/embed/dQw4w9WgXcQ", rendered)
        self.assertIn("https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg", rendered)

    def test_embeds_youtu_be_url_once(self):
        rendered = render_post_content(
            "짧은 주소 https://youtu.be/dQw4w9WgXcQ 같은 영상 https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )

        self.assertEqual(rendered.count("https://www.youtube.com/embed/dQw4w9WgXcQ"), 1)


class LoginFormRememberMeTests(SimpleTestCase):
    def test_remember_me_defaults_to_false(self):
        form = LoginForm(data={"email": "user@example.com", "password": "secret"})

        self.assertTrue(form.is_valid())
        self.assertFalse(form.cleaned_data["remember_me"])

    def test_remember_me_accepts_checked_value(self):
        form = LoginForm(data={"email": "user@example.com", "password": "secret", "remember_me": "on"})

        self.assertTrue(form.is_valid())
        self.assertTrue(form.cleaned_data["remember_me"])


class SoccerMatchPredictionStatusTests(SimpleTestCase):
    def test_unset_bet_is_pending(self):
        match = SoccerMatch(bet=None, result=None)

        self.assertEqual(match.prediction_status_label, "")
        self.assertEqual(match.prediction_status_class, "")

    def test_unset_bet_with_result_is_finished(self):
        match = SoccerMatch(bet=None, result=SoccerMatch.OUTCOME_HOME_WIN)

        self.assertEqual(match.prediction_status_label, "")
        self.assertEqual(match.prediction_status_class, "")
        self.assertEqual(match.home_win_button_class, "btn-primary")

    def test_bet_without_result_shows_prediction(self):
        match = SoccerMatch(bet=SoccerMatch.OUTCOME_DRAW, result=None)

        self.assertEqual(match.prediction_status_label, "")
        self.assertEqual(match.prediction_status_class, "")
        self.assertEqual(match.draw_button_class, "btn-success")

    def test_matching_result_is_hit(self):
        match = SoccerMatch(bet=SoccerMatch.OUTCOME_HOME_WIN, result=SoccerMatch.OUTCOME_HOME_WIN)

        self.assertEqual(match.prediction_status_label, "적중")
        self.assertEqual(match.prediction_status_class, "text-primary")
        self.assertEqual(match.home_win_button_class, "btn-primary")

    def test_different_result_is_miss(self):
        match = SoccerMatch(bet=SoccerMatch.OUTCOME_AWAY_WIN, result=SoccerMatch.OUTCOME_DRAW)

        self.assertEqual(match.prediction_status_label, "실패")
        self.assertEqual(match.prediction_status_class, "text-danger")
        self.assertEqual(match.draw_button_class, "btn-danger")
        self.assertEqual(match.away_win_button_class, "btn-success")


class MatchBetAccuracyTests(SimpleTestCase):
    def test_zero_completed_bets_shows_zero_percent(self):
        self.assertEqual(_format_accuracy_rate(0, 0), "0%")

    def test_integer_accuracy_omits_decimal(self):
        self.assertEqual(_format_accuracy_rate(2, 4), "50%")

    def test_fractional_accuracy_shows_one_decimal(self):
        self.assertEqual(_format_accuracy_rate(2, 3), "66.7%")

    @patch("board.views.SoccerMatch.objects")
    def test_accuracy_stats_include_completed_bet_count(self, soccer_match_objects):
        matches = MagicMock()
        soccer_match_objects.all.return_value = matches
        matches.aggregate.return_value = {
            "completed_bet_count": 5,
            "hit_count": 2,
        }

        self.assertEqual(
            _match_bet_accuracy_stats(),
            {"completed_bet_count": 5, "hit_count": 2, "accuracy": "40%"},
        )
        soccer_match_objects.all.assert_called_once_with()
        matches.filter.assert_not_called()

    @patch("board.views.SoccerMatch.objects")
    def test_accuracy_stats_can_be_scoped_by_year_and_league(self, soccer_match_objects):
        matches = MagicMock()
        year_matches = MagicMock()
        league_matches = MagicMock()
        soccer_match_objects.all.return_value = matches
        matches.filter.return_value = year_matches
        year_matches.filter.return_value = league_matches
        league_matches.aggregate.return_value = {
            "completed_bet_count": 4,
            "hit_count": 3,
        }

        self.assertEqual(
            _match_bet_accuracy_stats(year=2026, league="프리미어리그"),
            {"completed_bet_count": 4, "hit_count": 3, "accuracy": "75%"},
        )
        matches.filter.assert_called_once_with(year=2026)
        year_matches.filter.assert_called_once_with(league="프리미어리그")

    @patch("board.views.SoccerMatch.objects")
    def test_accuracy_stats_by_league_includes_empty_leagues(self, soccer_match_objects):
        matches = MagicMock()
        values = MagicMock()
        soccer_match_objects.filter.return_value = matches
        matches.values.return_value = values
        values.annotate.return_value = [
            {
                "league": "프리미어리그",
                "completed_bet_count": 5,
                "hit_count": 3,
            },
        ]

        self.assertEqual(
            _match_bet_accuracy_stats_by_league(2026, ["프리미어리그", "라리가"]),
            {
                "프리미어리그": {"completed_bet_count": 5, "hit_count": 3, "accuracy": "60%"},
                "라리가": {"completed_bet_count": 0, "hit_count": 0, "accuracy": "0%"},
            },
        )
        soccer_match_objects.filter.assert_called_once_with(
            year=2026,
            league__in=["프리미어리그", "라리가"],
        )
        matches.values.assert_called_once_with("league")
