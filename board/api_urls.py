from django.urls import path

from . import api


app_name = "board_api"

urlpatterns = [
    path("", api.api_root, name="root"),
    path("auth/signup/", api.signup, name="signup"),
    path("auth/login/", api.login, name="login"),
    path("auth/logout/", api.logout, name="logout"),
    path("auth/me/", api.me, name="me"),
    path("auth/password/reset/", api.password_reset, name="password_reset"),
    path("auth/password/change/", api.password_change, name="password_change"),
    path("home/", api.home, name="home"),
    path("ssul-posts/", api.ssul_posts, name="ssul_posts"),
    path("ssul-posts/<int:post_id>/", api.ssul_post_detail, name="ssul_post_detail"),
    path("ssul-posts/<int:post_id>/images/<int:image_id>/", api.ssul_post_image_detail, name="ssul_post_image_detail"),
    path("ssul-posts/<int:post_id>/like/", api.ssul_post_like, name="ssul_post_like"),
    path("ssul-posts/<int:post_id>/comments/", api.ssul_comments, name="ssul_comments"),
    path("posts/", api.posts, name="posts"),
    path("posts/<int:post_id>/", api.post_detail, name="post_detail"),
    path("posts/<int:post_id>/images/<int:image_id>/", api.post_image_detail, name="post_image_detail"),
    path("posts/<int:post_id>/like/", api.post_like, name="post_like"),
    path("posts/<int:post_id>/comments/", api.comments, name="comments"),
    path("comments/<int:comment_id>/", api.comment_detail, name="comment_detail"),
    path("info-posts/", api.info_posts, name="info_posts"),
    path("info-posts/<int:info_id>/", api.info_post_detail, name="info_post_detail"),
    path("info-posts/<int:info_id>/like/", api.info_like, name="info_like"),
    path("link-posts/", api.link_posts, name="link_posts"),
    path("link-posts/<int:link_id>/", api.link_post_detail, name="link_post_detail"),
    path("link-posts/<int:link_id>/recommend/", api.link_recommend, name="link_recommend"),
    path("matches/", api.matches, name="matches"),
    path("matches/<int:match_id>/", api.match_detail, name="match_detail"),
    path("matches/<int:match_id>/favorite/", api.match_favorite, name="match_favorite"),
    path("matches/<int:match_id>/bet/", api.match_bet, name="match_bet"),
]
