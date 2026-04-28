from django.test import SimpleTestCase

from board.templatetags.board_extras import render_post_content


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
