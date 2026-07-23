from django.test import SimpleTestCase
from unittest.mock import patch

from board.models import SoccerMatch
from board.templatetags.board_extras import render_post_content
from board.views import _format_accuracy_rate, _match_bet_accuracy_stats


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
        self.assertEqual(match.prediction_status_class, "text-danger")
        self.assertEqual(match.home_win_button_class, "btn-danger")

    def test_different_result_is_miss(self):
        match = SoccerMatch(bet=SoccerMatch.OUTCOME_AWAY_WIN, result=SoccerMatch.OUTCOME_DRAW)

        self.assertEqual(match.prediction_status_label, "실패")
        self.assertEqual(match.prediction_status_class, "text-success")
        self.assertEqual(match.draw_button_class, "btn-primary")
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
        soccer_match_objects.aggregate.return_value = {
            "completed_bet_count": 5,
            "hit_count": 2,
        }

        self.assertEqual(
            _match_bet_accuracy_stats(),
            {"completed_bet_count": 5, "accuracy": "40%"},
        )
