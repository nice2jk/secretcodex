import re
from urllib.parse import parse_qs, urlparse

from django import template
from django.template.defaultfilters import linebreaksbr, urlize
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()

URL_PATTERN = re.compile(r"https?://[^\s<]+")


def _extract_youtube_video_id(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path

    if host.endswith("youtu.be"):
        video_id = path.strip("/").split("/")[0]
        return video_id or None

    if "youtube.com" not in host:
        return None

    if path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]

    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
        return parts[1]
    return None


def _unique_youtube_embeds(text):
    embeds = []
    seen = set()
    for match in URL_PATTERN.finditer(text or ""):
        url = match.group(0).rstrip(".,)")
        video_id = _extract_youtube_video_id(url)
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        embeds.append(
            {
                "watch_url": f"https://www.youtube.com/watch?v={video_id}",
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            }
        )
    return embeds


@register.filter
def render_post_content(value):
    rendered_text = linebreaksbr(urlize(value or "", autoescape=True), autoescape=False)
    embeds = _unique_youtube_embeds(value)
    if not embeds:
        return rendered_text

    embed_html = format_html_join(
        "",
        """
        <div class="card border-0 bg-body-tertiary mt-4">
          <a href="{}" target="_blank" rel="noopener noreferrer" class="text-decoration-none">
            <img src="{}" alt="YouTube thumbnail" class="img-fluid rounded-top">
          </a>
          <div class="card-body">
            <div class="ratio ratio-16x9 rounded overflow-hidden">
              <iframe
                src="{}"
                title="YouTube video player"
                loading="lazy"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                referrerpolicy="strict-origin-when-cross-origin"
                allowfullscreen
              ></iframe>
            </div>
          </div>
        </div>
        """,
        ((embed["watch_url"], embed["thumbnail_url"], embed["embed_url"]) for embed in embeds),
    )
    return mark_safe(f"{rendered_text}{embed_html}")
