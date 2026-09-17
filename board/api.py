import json
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import AnonymousUser, User
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.crypto import get_random_string
from django.views.decorators.csrf import csrf_exempt

from .models import Comment, InfoPost, LinkPost, Post, PostImage, Profile, SoccerMatch
from .views import (
    MATCH_BET_VALUES,
    _can_set_match_bet,
    _get_display_name,
    _match_bet_accuracy_stats,
    _match_bet_accuracy_stats_by_league,
    _match_bet_payload,
    _match_favorite_payload,
)


API_TOKEN_SALT = "board.api.auth"
API_TOKEN_MAX_AGE = getattr(settings, "API_TOKEN_MAX_AGE", 60 * 60 * 24 * 14)
SSUL_POST_CATEGORY = "common"
POST_CATEGORIES = {"common", "secret"}
INFO_CATEGORIES = {"thread", "ai"}
LINK_CATEGORIES = {choice[0] for choice in LinkPost.CATEGORY_CHOICES}
MATCH_YEARS = [2027, 2026]
MATCH_LEAGUES = ["프리미어리그", "라리가", "분데스리가", "대표"]


def _json_response(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _error(message, status=400, code=None, errors=None):
    payload = {"error": message}
    if code:
        payload["code"] = code
    if errors:
        payload["errors"] = errors
    return _json_response(payload, status=status)


def _parse_payload(request):
    content_type = request.META.get("CONTENT_TYPE", "")
    if content_type.startswith("application/json"):
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON")
    return request.POST.dict()


def _api_view(methods, require_auth=False, optional_auth=True):
    allowed_methods = {method.upper() for method in methods}

    def decorator(func):
        @csrf_exempt
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if request.method not in allowed_methods:
                return _error("Method not allowed", status=405)

            user, auth_error = _authenticate_request(request)
            if auth_error:
                return auth_error
            if require_auth and not user.is_authenticated:
                return _error("Authentication required", status=401, code="authentication_required")
            if not optional_auth and not require_auth:
                user = AnonymousUser()
            request.api_user = user
            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def _create_token(user):
    payload = {
        "user_id": user.id,
        "auth_hash": user.get_session_auth_hash(),
    }
    return signing.dumps(payload, salt=API_TOKEN_SALT)


def _authenticate_request(request):
    header = request.headers.get("Authorization", "")
    if not header:
        return AnonymousUser(), None
    if not header.startswith("Bearer "):
        return AnonymousUser(), _error("Invalid authorization header", status=401)

    token = header.split(" ", 1)[1].strip()
    try:
        payload = signing.loads(token, salt=API_TOKEN_SALT, max_age=API_TOKEN_MAX_AGE)
        user = User.objects.select_related("profile").get(id=payload.get("user_id"), is_active=True)
    except signing.SignatureExpired:
        return AnonymousUser(), _error("Token expired", status=401, code="token_expired")
    except (signing.BadSignature, User.DoesNotExist):
        return AnonymousUser(), _error("Invalid token", status=401, code="invalid_token")

    if payload.get("auth_hash") != user.get_session_auth_hash():
        return AnonymousUser(), _error("Invalid token", status=401, code="invalid_token")
    return user, None


def _absolute_media_url(request, field_file):
    if not field_file:
        return None
    try:
        return request.build_absolute_uri(field_file.url)
    except ValueError:
        return None


def _paginate(request, queryset, per_page=20):
    try:
        requested_per_page = int(request.GET.get("per_page", per_page))
    except (TypeError, ValueError):
        requested_per_page = per_page
    requested_per_page = max(1, min(requested_per_page, 50))

    paginator = Paginator(queryset, requested_per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    return page_obj, {
        "page": page_obj.number,
        "per_page": requested_per_page,
        "total_pages": paginator.num_pages,
        "total_count": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }


def _is_named_author(user, author):
    return user.is_authenticated and (_get_display_name(user) == author or user.is_staff or user.is_superuser)


def _serialize_user(user):
    profile = getattr(user, "profile", None)
    return {
        "id": user.id,
        "email": user.username,
        "nickname": profile.nickname if profile else user.get_username(),
        "points": profile.points if profile else 0,
        "is_temporary_password": profile.is_temporary_password if profile else False,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def _serialize_image(request, image):
    return {
        "id": image.id,
        "url": _absolute_media_url(request, image.image),
        "created_at": image.created_at.isoformat(),
    }


def _serialize_comment(comment, user=None):
    user = user or AnonymousUser()
    return {
        "id": comment.id,
        "post_id": comment.post_id,
        "author": comment.author,
        "content": comment.content,
        "created_at": comment.created_at.isoformat(),
        "is_author": _is_named_author(user, comment.author),
    }


def _serialize_post(request, post, detail=False):
    user = getattr(request, "api_user", AnonymousUser())
    payload = {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "category": post.category,
        "author": post.author,
        "created_at": post.created_at.isoformat(),
        "views": post.views,
        "is_recommended": post.is_recommended,
        "like_count": getattr(post, "like_count", post.likes.count()),
        "is_liked": user.is_authenticated and post.likes.filter(id=user.id).exists(),
        "is_author": _is_named_author(user, post.author),
        "images": [_serialize_image(request, image) for image in post.images.all()],
    }
    if detail:
        payload["comments"] = [_serialize_comment(comment, user) for comment in post.comments.order_by("created_at")]
    return payload


def _serialize_info_post(post, user=None):
    user = user or AnonymousUser()
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "category": post.category,
        "author": post.author,
        "created_at": post.created_at.isoformat(),
        "like_count": getattr(post, "like_count", post.likes.count()),
        "is_liked": user.is_authenticated and post.likes.filter(id=user.id).exists(),
        "is_author": _is_named_author(user, post.author),
    }


def _serialize_link_post(post, user=None):
    user = user or AnonymousUser()
    return {
        "id": post.id,
        "category": post.category,
        "category_label": post.get_category_display(),
        "title": post.title,
        "url": post.url,
        "author": post.author,
        "created_at": post.created_at.isoformat(),
        "is_recommended": post.is_recommended,
        "link_id": post.link_id,
        "is_author": _is_named_author(user, post.author),
    }


def _serialize_match(match):
    return {
        "id": match.id,
        "match_id": match.match_id,
        "round_num": match.round_num,
        "match_date": match.match_date.isoformat(),
        "league": match.league,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "score": match.score,
        "result": match.result,
        "result_label": match.get_result_display() if match.result is not None else "",
        "bet": match.bet,
        "bet_label": match.get_bet_display() if match.bet is not None else "",
        "prediction_status_label": match.prediction_status_label,
        "prediction_status_class": match.prediction_status_class,
        "year": match.year,
        "is_favorite": match.is_recommended,
        "liked_at": match.liked_at.isoformat() if match.liked_at else None,
        "created_at": match.created_at.isoformat(),
    }


def _validate_post_payload(data, partial=False):
    errors = {}
    title = data.get("title")
    content = data.get("content")
    if not partial or title is not None:
        if not title or not str(title).strip():
            errors["title"] = ["제목을 입력하세요."]
        elif len(str(title)) > 200:
            errors["title"] = ["제목은 최대 200자까지 가능합니다."]
    if not partial or content is not None:
        if not content or not str(content).strip():
            errors["content"] = ["내용을 입력하세요."]
    return errors


def _validate_info_payload(data, partial=False):
    errors = _validate_post_payload(data, partial=partial)
    content = data.get("content")
    if content is not None and len(str(content)) > 500:
        errors["content"] = ["내용은 최대 500자까지 가능합니다."]
    return errors


def _validate_link_payload(data, partial=False):
    errors = {}
    title = data.get("title")
    url = data.get("url")
    category = data.get("category")
    if not partial or title is not None:
        if not title or not str(title).strip():
            errors["title"] = ["제목을 입력하세요."]
        elif len(str(title)) > 200:
            errors["title"] = ["제목은 최대 200자까지 가능합니다."]
    if not partial or url is not None:
        if not url or not str(url).strip():
            errors["url"] = ["URL을 입력하세요."]
    if category is not None and category not in LINK_CATEGORIES:
        errors["category"] = ["올바른 카테고리를 입력하세요."]
    return errors


def _list_posts(request, category):
    if category not in POST_CATEGORIES:
        return _error("Invalid category")
    if category == "secret" and not request.api_user.is_authenticated:
        return _error("Authentication required", status=401)

    queryset = (
        Post.objects.filter(category=category)
        .annotate(like_count=Count("likes"))
        .prefetch_related("images", "likes")
        .order_by("-id")
    )
    query = request.GET.get("q", "").strip()
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(content__icontains=query) | Q(author__icontains=query))
    if request.GET.get("recommended") == "1":
        queryset = queryset.filter(like_count__gt=0).order_by("-like_count", "-id")
    page_obj, pagination = _paginate(request, queryset)
    return _json_response({"results": [_serialize_post(request, post) for post in page_obj], "pagination": pagination})


def _create_post(request, fixed_category=None):
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")

    category = fixed_category or data.get("category", SSUL_POST_CATEGORY)
    if category not in POST_CATEGORIES:
        return _error("Invalid category")
    if category == "secret" and not request.api_user.is_authenticated:
        return _error("Authentication required", status=401)

    errors = _validate_post_payload(data)
    images = request.FILES.getlist("images")
    if len(images) > 3:
        errors["images"] = ["이미지는 최대 3장까지 업로드할 수 있습니다."]
    if errors:
        return _error("Validation failed", errors=errors)

    post = Post.objects.create(
        title=str(data["title"]).strip(),
        content=str(data["content"]).strip(),
        category=category,
        author=_get_display_name(request.api_user) if request.api_user.is_authenticated else "익명",
    )
    for image in images[:3]:
        PostImage.objects.create(post=post, image=image)
    if request.api_user.is_authenticated and hasattr(request.api_user, "profile"):
        request.api_user.profile.points += 10
        request.api_user.profile.save(update_fields=["points"])
    return _json_response({"post": _serialize_post(request, post, detail=True)}, status=201)


def _get_post(post_id, category=None, queryset=None):
    if queryset is None:
        queryset = Post.objects.all()
    if category is not None:
        queryset = queryset.filter(category=category)
    return get_object_or_404(queryset, id=post_id)


def _post_detail_response(request, post_id, category=None):
    queryset = Post.objects.prefetch_related("images", "likes", "comments")
    post = _get_post(post_id, category=category, queryset=queryset)
    if post.category == "secret" and not request.api_user.is_authenticated:
        return _error("Authentication required", status=401)

    if request.method == "GET":
        post.views = F("views") + 1
        post.save(update_fields=["views"])
        post.refresh_from_db()
        return _json_response({"post": _serialize_post(request, post, detail=True)})

    if not _is_named_author(request.api_user, post.author):
        return _error("Permission denied", status=403)

    if request.method == "DELETE":
        post.delete()
        return _json_response({"message": "success"})

    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")

    errors = _validate_post_payload(data, partial=True)
    existing_count = post.images.count()
    remaining = max(0, 3 - existing_count)
    images = request.FILES.getlist("images")
    if len(images) > remaining:
        errors["images"] = [f"이미지는 최대 3장까지 업로드할 수 있습니다. 현재 {existing_count}장 등록됨."]
    if errors:
        return _error("Validation failed", errors=errors)

    if "title" in data:
        post.title = str(data["title"]).strip()
    if "content" in data:
        post.content = str(data["content"]).strip()
    post.save()
    for image in images[:remaining]:
        PostImage.objects.create(post=post, image=image)
    return _json_response({"post": _serialize_post(request, post, detail=True)})


def _post_image_detail_response(request, post_id, image_id, category=None):
    post = _get_post(post_id, category=category)
    if not _is_named_author(request.api_user, post.author):
        return _error("Permission denied", status=403)
    image = get_object_or_404(PostImage, id=image_id, post=post)
    image.delete()
    return _json_response({"message": "success"})


def _post_like_response(request, post_id, category=None):
    post = _get_post(post_id, category=category)
    if post.category == "secret" and not request.api_user.is_authenticated:
        return _error("Authentication required", status=401)
    if post.likes.filter(id=request.api_user.id).exists():
        post.likes.remove(request.api_user)
        is_liked = False
    else:
        post.likes.add(request.api_user)
        is_liked = True
    return _json_response({"like_count": post.likes.count(), "is_liked": is_liked})


def _comments_response(request, post_id, category=None):
    post = _get_post(post_id, category=category)
    if post.category == "secret" and not request.api_user.is_authenticated:
        return _error("Authentication required", status=401)

    if request.method == "GET":
        queryset = post.comments.order_by("created_at")
        page_obj, pagination = _paginate(request, queryset)
        return _json_response({"results": [_serialize_comment(comment, request.api_user) for comment in page_obj], "pagination": pagination})

    if not request.api_user.is_authenticated:
        return _error("Authentication required", status=401)
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    content = str(data.get("content", "")).strip()
    if not content:
        return _error("내용을 입력하세요.")

    comment = Comment.objects.create(post=post, author=_get_display_name(request.api_user), content=content)
    if hasattr(request.api_user, "profile"):
        request.api_user.profile.points += 3
        request.api_user.profile.save(update_fields=["points"])
    return _json_response({"comment": _serialize_comment(comment, request.api_user)}, status=201)


@_api_view(["GET"])
def api_root(request):
    return _json_response(
        {
            "name": "secretcodex API",
            "version": "v1",
            "endpoints": {
                "auth": "/api/v1/auth/",
                "home": "/api/v1/home/",
                "posts": "/api/v1/posts/",
                "ssul_posts": "/api/v1/ssul-posts/",
                "info_posts": "/api/v1/info-posts/",
                "link_posts": "/api/v1/link-posts/",
                "matches": "/api/v1/matches/",
            },
        }
    )


@_api_view(["POST"])
def signup(request):
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")

    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    nickname = str(data.get("nickname", "")).strip()
    errors = {}
    if not email:
        errors["email"] = ["이메일을 입력하세요."]
    elif User.objects.filter(username=email).exists():
        errors["email"] = ["이미 사용 중인 이메일입니다."]
    if not password:
        errors["password"] = ["비밀번호를 입력하세요."]
    if not nickname:
        errors["nickname"] = ["닉네임을 입력하세요."]
    elif Profile.objects.filter(nickname=nickname).exists():
        errors["nickname"] = ["이미 사용 중인 닉네임입니다."]
    if errors:
        return _error("Validation failed", status=400, errors=errors)

    user = User.objects.create_user(username=email, email=email, password=password)
    Profile.objects.create(user=user, nickname=nickname, points=10)
    return _json_response({"token": _create_token(user), "user": _serialize_user(user)}, status=201)


@_api_view(["POST"])
def login(request):
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")

    user = authenticate(request, username=data.get("email"), password=data.get("password"))
    if user is None:
        return _error("이메일 또는 비밀번호가 올바르지 않습니다.", status=401)
    return _json_response({"token": _create_token(user), "user": _serialize_user(user)})


@_api_view(["POST"], require_auth=True)
def logout(request):
    return _json_response({"message": "success"})


@_api_view(["GET"], require_auth=True)
def me(request):
    display_name = _get_display_name(request.api_user)
    return _json_response(
        {
            "user": _serialize_user(request.api_user),
            "stats": {
                "post_count": Post.objects.filter(author=display_name).count(),
                "comment_count": Comment.objects.filter(author=display_name).count(),
            },
        }
    )


@_api_view(["POST"])
def password_reset(request):
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")

    email = str(data.get("email", "")).strip()
    nickname = str(data.get("nickname", "")).strip()
    try:
        user = User.objects.select_related("profile").get(username=email)
        if user.profile.nickname != nickname:
            raise User.DoesNotExist
    except User.DoesNotExist:
        return _error("이메일 또는 닉네임이 일치하지 않습니다.", status=400)

    temp_password = get_random_string(10)
    user.set_password(temp_password)
    user.save(update_fields=["password"])
    user.profile.is_temporary_password = True
    user.profile.save(update_fields=["is_temporary_password"])
    return _json_response({"temporary_password": temp_password})


@_api_view(["POST"], require_auth=True)
def password_change(request):
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")

    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")
    if not new_password:
        return _error("새 비밀번호를 입력하세요.")
    if new_password != confirm_password:
        return _error("비밀번호가 일치하지 않습니다.")

    request.api_user.set_password(new_password)
    request.api_user.save(update_fields=["password"])
    if hasattr(request.api_user, "profile"):
        request.api_user.profile.is_temporary_password = False
        request.api_user.profile.save(update_fields=["is_temporary_password"])
    return _json_response({"token": _create_token(request.api_user), "user": _serialize_user(request.api_user)})


@_api_view(["GET"])
def home(request):
    user = request.api_user
    target_categories = ["best", "xart", "movie", "itnews", "ground", "stock"]
    return _json_response(
        {
            "recent_posts": [
                _serialize_post(request, post)
                for post in Post.objects.filter(category="common").prefetch_related("images", "likes").order_by("-created_at")[:5]
            ],
            "recent_threads": [
                _serialize_info_post(post, user)
                for post in InfoPost.objects.filter(category="thread").annotate(like_count=Count("likes")).order_by("-created_at")[:5]
            ],
            "recent_ai_news": [
                _serialize_info_post(post, user)
                for post in InfoPost.objects.filter(category="ai").annotate(like_count=Count("likes")).order_by("-created_at")[:5]
            ],
            "recommended_posts": [
                _serialize_post(request, post)
                for post in (
                    Post.objects.filter(category="common")
                    .annotate(like_count=Count("likes"))
                    .filter(like_count__gt=0)
                    .prefetch_related("images", "likes")
                    .order_by("-like_count", "-id")[:5]
                )
            ],
            "popular_links": [
                _serialize_link_post(post, user)
                for post in LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]
            ],
            "recent_best_links": [
                _serialize_link_post(post, user)
                for post in LinkPost.objects.filter(category="best").order_by("-id")[:7]
            ],
        }
    )


@_api_view(["GET", "POST"])
def posts(request):
    if request.method == "GET":
        category = request.GET.get("category", "common")
        return _list_posts(request, category)
    return _create_post(request)


@_api_view(["GET", "POST"])
def ssul_posts(request):
    if request.method == "GET":
        return _list_posts(request, SSUL_POST_CATEGORY)
    return _create_post(request, fixed_category=SSUL_POST_CATEGORY)


@_api_view(["GET", "PATCH", "DELETE"])
def post_detail(request, post_id):
    return _post_detail_response(request, post_id)


@_api_view(["GET", "PATCH", "DELETE"])
def ssul_post_detail(request, post_id):
    return _post_detail_response(request, post_id, category=SSUL_POST_CATEGORY)


@_api_view(["DELETE"], require_auth=True)
def post_image_detail(request, post_id, image_id):
    return _post_image_detail_response(request, post_id, image_id)


@_api_view(["DELETE"], require_auth=True)
def ssul_post_image_detail(request, post_id, image_id):
    return _post_image_detail_response(request, post_id, image_id, category=SSUL_POST_CATEGORY)


@_api_view(["POST"], require_auth=True)
def post_like(request, post_id):
    return _post_like_response(request, post_id)


@_api_view(["POST"], require_auth=True)
def ssul_post_like(request, post_id):
    return _post_like_response(request, post_id, category=SSUL_POST_CATEGORY)


@_api_view(["GET", "POST"])
def comments(request, post_id):
    return _comments_response(request, post_id)


@_api_view(["GET", "POST"])
def ssul_comments(request, post_id):
    return _comments_response(request, post_id, category=SSUL_POST_CATEGORY)


@_api_view(["DELETE"], require_auth=True)
def comment_detail(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if not _is_named_author(request.api_user, comment.author):
        return _error("Permission denied", status=403)
    comment.delete()
    return _json_response({"message": "success"})


@_api_view(["GET", "POST"])
def info_posts(request):
    if request.method == "GET":
        category = request.GET.get("category", "thread")
        if category not in INFO_CATEGORIES:
            return _error("Invalid category")
        queryset = InfoPost.objects.filter(category=category).annotate(like_count=Count("likes")).prefetch_related("likes").order_by("-created_at")
        query = request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(content__icontains=query) | Q(author__icontains=query))
        page_obj, pagination = _paginate(request, queryset)
        return _json_response({"results": [_serialize_info_post(post, request.api_user) for post in page_obj], "pagination": pagination})

    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    category = data.get("category", "thread")
    if category not in INFO_CATEGORIES:
        return _error("Invalid category")
    errors = _validate_info_payload(data)
    if errors:
        return _error("Validation failed", errors=errors)

    post = InfoPost.objects.create(
        title=str(data["title"]).strip(),
        content=str(data["content"]).strip(),
        category=category,
        author=_get_display_name(request.api_user) if request.api_user.is_authenticated else str(data.get("author", "익명")).strip() or "익명",
    )
    return _json_response({"post": _serialize_info_post(post, request.api_user)}, status=201)


@_api_view(["GET", "PATCH", "DELETE"])
def info_post_detail(request, info_id):
    post = get_object_or_404(InfoPost.objects.prefetch_related("likes"), id=info_id)
    if request.method == "GET":
        return _json_response({"post": _serialize_info_post(post, request.api_user)})
    if not _is_named_author(request.api_user, post.author):
        return _error("Permission denied", status=403)
    if request.method == "DELETE":
        post.delete()
        return _json_response({"message": "success"})

    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    errors = _validate_info_payload(data, partial=True)
    if errors:
        return _error("Validation failed", errors=errors)
    if "title" in data:
        post.title = str(data["title"]).strip()
    if "content" in data:
        post.content = str(data["content"]).strip()
    post.save()
    return _json_response({"post": _serialize_info_post(post, request.api_user)})


@_api_view(["POST"], require_auth=True)
def info_like(request, info_id):
    post = get_object_or_404(InfoPost, id=info_id)
    if post.likes.filter(id=request.api_user.id).exists():
        post.likes.remove(request.api_user)
        is_liked = False
    else:
        post.likes.add(request.api_user)
        is_liked = True
    return _json_response({"like_count": post.likes.count(), "is_liked": is_liked})


@_api_view(["GET", "POST"])
def link_posts(request):
    if request.method == "GET":
        category = request.GET.get("category")
        queryset = LinkPost.objects.all().order_by("-id")
        if category:
            if category == "popular":
                queryset = queryset.filter(category__in=LINK_CATEGORIES, is_recommended=True).order_by("-created_at")
            elif category in LINK_CATEGORIES:
                queryset = queryset.filter(category=category)
            else:
                return _error("Invalid category")
        query = request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(url__icontains=query) | Q(author__icontains=query))
        page_obj, pagination = _paginate(request, queryset)
        return _json_response({"results": [_serialize_link_post(post, request.api_user) for post in page_obj], "pagination": pagination})

    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    category = data.get("category", "best")
    data["category"] = category
    errors = _validate_link_payload(data)
    if errors:
        return _error("Validation failed", errors=errors)

    post = LinkPost(
        category=category,
        title=str(data["title"]).strip(),
        url=str(data["url"]).strip(),
        author=_get_display_name(request.api_user) if request.api_user.is_authenticated else str(data.get("author", "익명")).strip() or "익명",
    )
    try:
        post.full_clean()
        post.save()
    except ValidationError as exc:
        return _error("Validation failed", errors=exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages})
    return _json_response({"post": _serialize_link_post(post, request.api_user)}, status=201)


@_api_view(["GET", "PATCH", "DELETE"])
def link_post_detail(request, link_id):
    post = get_object_or_404(LinkPost, id=link_id)
    if request.method == "GET":
        return _json_response({"post": _serialize_link_post(post, request.api_user)})
    if not _is_named_author(request.api_user, post.author):
        return _error("Permission denied", status=403)
    if request.method == "DELETE":
        post.delete()
        return _json_response({"message": "success"})

    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    errors = _validate_link_payload(data, partial=True)
    if errors:
        return _error("Validation failed", errors=errors)
    if "category" in data:
        post.category = data["category"]
    if "title" in data:
        post.title = str(data["title"]).strip()
    if "url" in data:
        post.url = str(data["url"]).strip()
    if "author" in data and request.api_user.is_staff:
        post.author = str(data["author"]).strip() or "익명"
    try:
        post.full_clean()
        post.save()
    except ValidationError as exc:
        return _error("Validation failed", errors=exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages})
    return _json_response({"post": _serialize_link_post(post, request.api_user)})


@_api_view(["POST"])
def link_recommend(request, link_id):
    post = get_object_or_404(LinkPost, id=link_id)
    post.is_recommended = not post.is_recommended
    post.save(update_fields=["is_recommended"])
    return _json_response({"is_recommended": post.is_recommended})


@_api_view(["GET"])
def matches(request):
    try:
        selected_year = int(request.GET.get("year", MATCH_YEARS[0]))
    except (TypeError, ValueError):
        selected_year = MATCH_YEARS[0]
    if selected_year not in MATCH_YEARS:
        selected_year = MATCH_YEARS[0]

    selected_league = request.GET.get("league", MATCH_LEAGUES[0])
    if selected_league not in MATCH_LEAGUES:
        selected_league = MATCH_LEAGUES[0]

    tab = request.GET.get("tab", "schedule")
    if tab == "results":
        queryset = SoccerMatch.objects.filter(league=selected_league, year=selected_year).exclude(score__isnull=True).exclude(score="").order_by("-match_id")
    elif tab == "predictions":
        queryset = SoccerMatch.objects.filter(league=selected_league, year=selected_year, bet__isnull=False).order_by("-match_id")
    elif tab == "favorites":
        queryset = SoccerMatch.objects.filter(is_recommended=True).order_by("match_date", "id")
    else:
        tab = "schedule"
        queryset = SoccerMatch.objects.filter(Q(score__isnull=True) | Q(score=""), league=selected_league, year=selected_year).order_by("match_id")

    page_obj, pagination = _paginate(request, queryset)
    league_accuracy_stats = _match_bet_accuracy_stats_by_league(selected_year, MATCH_LEAGUES)
    return _json_response(
        {
            "results": [_serialize_match(match) for match in page_obj],
            "pagination": pagination,
            "filters": {
                "years": MATCH_YEARS,
                "selected_year": selected_year,
                "leagues": [{"label": league, "value": league, "bet_stats": league_accuracy_stats[league]} for league in MATCH_LEAGUES],
                "selected_league": selected_league,
                "selected_tab": tab,
            },
            "bet_stats": _match_bet_accuracy_stats(year=selected_year),
            "can_set_match_bet": _can_set_match_bet(request.api_user),
        }
    )


@_api_view(["GET"])
def match_detail(request, match_id):
    match = get_object_or_404(SoccerMatch, id=match_id)
    return _json_response({"match": _serialize_match(match)})


@_api_view(["POST"])
def match_favorite(request, match_id):
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    replace_oldest = bool(data.get("replace_oldest"))

    with transaction.atomic():
        match = get_object_or_404(SoccerMatch.objects.select_for_update(), id=match_id)
        if match.is_recommended:
            match.is_recommended = False
            match.liked_at = None
            match.save(update_fields=["is_recommended", "liked_at"])
            return _json_response({"is_favorite": False, "favorite_count": SoccerMatch.objects.filter(is_recommended=True).count()})

        favorite_matches = (
            SoccerMatch.objects.select_for_update()
            .filter(is_recommended=True)
            .exclude(id=match.id)
            .order_by("liked_at", "id")
        )
        favorite_count = favorite_matches.count()
        if favorite_count >= 10 and not replace_oldest:
            return _json_response(
                {
                    "requires_confirmation": True,
                    "is_favorite": False,
                    "message": "즐겨찾기 10게임입니다. 오래된 경기를 삭제할까요?",
                }
            )

        removed_match_id = None
        if favorite_count >= 10:
            oldest_match = favorite_matches.first()
            if oldest_match:
                removed_match_id = oldest_match.id
                oldest_match.is_recommended = False
                oldest_match.liked_at = None
                oldest_match.save(update_fields=["is_recommended", "liked_at"])

        match.is_recommended = True
        from django.utils import timezone

        match.liked_at = timezone.now()
        match.save(update_fields=["is_recommended", "liked_at"])

    return _json_response(
        {
            "is_favorite": True,
            "removed_match_id": removed_match_id,
            "favorite_count": SoccerMatch.objects.filter(is_recommended=True).count(),
            "match": _match_favorite_payload(match),
        }
    )


@_api_view(["POST"], require_auth=True)
def match_bet(request, match_id):
    if not _can_set_match_bet(request.api_user):
        return _error("Permission denied", status=403)
    try:
        data = _parse_payload(request)
    except ValueError:
        return _error("Invalid JSON")
    try:
        bet = int(data.get("bet"))
    except (TypeError, ValueError):
        return _error("Invalid bet")
    if bet not in MATCH_BET_VALUES:
        return _error("Invalid bet")

    with transaction.atomic():
        match = get_object_or_404(SoccerMatch.objects.select_for_update(), id=match_id)
        if match.result is not None:
            return _json_response({"error": "Match already finished", "match": _match_bet_payload(match)}, status=409)
        if match.bet is not None:
            return _json_response({"error": "Bet already set", "match": _match_bet_payload(match)}, status=409)
        match.bet = bet
        match.save(update_fields=["bet"])
    return _json_response({"message": "success", "match": _match_bet_payload(match)})
