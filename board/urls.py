from django.urls import path

from . import views

app_name = "board"

urlpatterns = [
    path("", views.home, name="home"),
    path("board/", views.post_list, name="post_list"),
    path("board/new/", views.post_create, name="post_create"),
    path("board/<int:post_id>/", views.post_detail, name="post_detail"),
    path("board/<int:post_id>/edit/", views.post_edit, name="post_edit"),
    path("board/<int:post_id>/delete/", views.post_delete, name="post_delete"),
    path("board/<int:post_id>/images/<int:image_id>/delete/", views.post_image_delete, name="post_image_delete"),
    path("board/<int:post_id>/like/", views.post_like, name="post_like"),
    path("menu3/", views.link_list, name="link_list"),
    path("menu3/new/", views.link_create, name="link_create"),
    path("menu4/", views.menu4, name="menu4"),
    path("menu5/", views.menu5, name="menu5"),
    path("menu6/", views.menu6, name="menu6"),
    path("menu6/new/", views.link_create, name="link_create_best"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password/reset/", views.password_reset, name="password_reset"),
    path("password/change/", views.password_change, name="password_change"),
    path("profile/", views.profile, name="profile"),
]
