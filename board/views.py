import json
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.db import connection
from django.db.models import Count, F, Q
from django.utils.crypto import get_random_string
from django.utils import timezone
from .forms import CommentForm, LinkPostForm, PostForm, SignUpForm, LoginForm, PasswordResetForm, PasswordChangeForm, InfoPostForm, ThreadPostForm
from .models import Comment, LinkPost, Post, PostImage, Profile, InfoPost, SoccerMatch


MAX_FAVORITE_MATCHES = 10
MATCH_BET_VALUES = {0, 1, 2}


def _get_display_name(user):
    if hasattr(user, "profile"):
        return user.profile.nickname
    return user.get_username()


def _save_post_images(post, images, remaining):
    for image in images[:remaining]:
        PostImage.objects.create(post=post, image=image)


def _match_favorite_payload(match):
    score = f" ({match.score})" if match.score else ""
    round_label = f"[{match.round_num}]" if match.round_num else ""
    title = f"{match.home_team} vs {match.away_team}{score}"
    local_match_date = timezone.localtime(match.match_date, ZoneInfo("Asia/Seoul"))
    query = quote_plus(f"{match.home_team} vs {match.away_team}")
    return {
        "id": match.id,
        "round_label": round_label,
        "title": title,
        "meta": f"{match.league} · {local_match_date:%Y-%m-%d %H:%M}",
        "sort_key": int(match.match_date.timestamp()),
        "url": f"https://www.google.com/search?q={query}",
    }


def _can_set_match_bet(user):
    if not user.is_authenticated:
        return False

    with connection.cursor() as cursor:
        cursor.execute("SELECT is_superuser FROM auth_user WHERE id = %s", [user.id])
        row = cursor.fetchone()

    if not row:
        return False

    try:
        return int(row[0]) == 2
    except (TypeError, ValueError):
        return False


def _match_bet_payload(match):
    return {
        'bet': match.bet,
        'status_label': match.prediction_status_label,
        'status_class': match.prediction_status_class,
        'button_classes': {
            '1': match.home_win_button_class,
            '0': match.draw_button_class,
            '2': match.away_win_button_class,
        },
    }


def _format_accuracy_rate(hit_count, bet_count):
    if bet_count == 0:
        return '0%'

    rate = hit_count * 100 / bet_count
    if rate.is_integer():
        return f'{int(rate)}%'
    return f'{rate:.1f}%'


def _match_bet_accuracy_stats():
    stats = SoccerMatch.objects.aggregate(
        bet_count=Count('id', filter=Q(bet__isnull=False)),
        hit_count=Count('id', filter=Q(bet__isnull=False, result=F('bet'))),
    )
    bet_count = stats['bet_count'] or 0
    return {
        'bet_count': bet_count,
        'accuracy': _format_accuracy_rate(stats['hit_count'] or 0, bet_count),
    }


def home(request):
    recent_posts = Post.objects.order_by("-created_at")[:5]
    recent_links = InfoPost.objects.filter(category='thread').order_by("-created_at")[:5]
    recent_ai_news = InfoPost.objects.filter(category='ai').order_by("-created_at")[:5]
    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]
    recent_best = LinkPost.objects.filter(category='best').order_by("-id")[:7]
    return render(
        request,
        "board/home.html",
        {
            "recent_posts": recent_posts,
            "recent_links": recent_links,
            "recent_ai_news": recent_ai_news,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
            "recent_best": recent_best,
        },
    )


def post_list(request):
    posts = Post.objects.filter(category='common').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/post_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )


def post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            images = request.FILES.getlist("images")
            if len(images) > 3:
                form.add_error(None, "이미지는 최대 3장까지 업로드할 수 있습니다.")
            else:
                post = form.save(commit=False)
                if request.user.is_authenticated:
                    post.author = _get_display_name(request.user)
                else:
                    post.author = "익명"
                post.category = 'common'
                post.save()
                _save_post_images(post, images, 3)
                if request.user.is_authenticated and hasattr(request.user, "profile"):
                    request.user.profile.points += 10
                    request.user.profile.save()
                return redirect("board:post_detail", post_id=post.id)
    else:
        form = PostForm()
    return render(
        request,
        "board/post_form.html",
        {"form": form, "remaining_slots": list(range(3))},
    )


def post_detail(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    post.views += 1
    post.save()
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect("board:login")
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = _get_display_name(request.user)
            comment.save()
            if hasattr(request.user, "profile"):
                request.user.profile.points += 3
                request.user.profile.save()
            return redirect("board:post_detail", post_id=post.id)
    else:
        form = CommentForm()
    is_author = request.user.is_authenticated and _get_display_name(request.user) == post.author

    previous_post = Post.objects.filter(category=post.category, id__lt=post.id).order_by('-id').first()
    next_post = Post.objects.filter(category=post.category, id__gt=post.id).order_by('id').first()

    return render(
        request,
        "board/post_detail.html",
        {"post": post, "form": form, "is_author": is_author, "previous_post": previous_post, "next_post": next_post},
    )


@login_required
def post_edit(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if _get_display_name(request.user) != post.author:
        return redirect("board:post_detail", post_id=post.id)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            images = request.FILES.getlist("images")
            existing_count = post.images.count()
            remaining = max(0, 3 - existing_count)
            if len(images) > remaining:
                form.add_error(
                    None,
                    f"이미지는 최대 3장까지 업로드할 수 있습니다. 현재 {existing_count}장 등록됨.",
                )
            else:
                form.save()
                _save_post_images(post, images, remaining)
                return redirect("board:post_detail", post_id=post.id)
    else:
        form = PostForm(instance=post)
    remaining = max(0, 3 - post.images.count())
    return render(
        request,
        "board/post_form.html",
        {
            "form": form,
            "is_edit": True,
            "post": post,
            "images": post.images.all(),
            "remaining_slots": list(range(remaining)),
        },
    )


@login_required
def post_image_delete(request, post_id, image_id):
    post = get_object_or_404(Post, id=post_id)
    if _get_display_name(request.user) != post.author:
        if post.category == "secret":
            return redirect("board:secret_detail", post_id=post.id)
        return redirect("board:post_detail", post_id=post.id)
    image = get_object_or_404(PostImage, id=image_id, post=post)
    if request.method == "POST":
        image.delete()
    if post.category == "secret":
        return redirect("board:secret_edit", post_id=post.id)
    return redirect("board:post_edit", post_id=post.id)


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if _get_display_name(request.user) != post.author:
        return redirect("board:post_detail", post_id=post.id)
    if request.method == "POST":
        post.delete()
        return redirect("board:post_list")
    return redirect("board:post_detail", post_id=post.id)


def link_list(request):
    links = InfoPost.objects.filter(category='thread').order_by("-created_at")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.like_count = link.likes.count()
        if request.user.is_authenticated:
            link.is_liked = link.likes.filter(id=request.user.id).exists()
        else:
            link.is_liked = False

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/link_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "board_type": "thread",
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )


def info_create(request):
    if request.method == "POST":
        form = ThreadPostForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            if request.user.is_authenticated:
                link.author = _get_display_name(request.user)
            link.category = 'thread'
            link.save()
            return redirect("board:link_list")
    else:
        initial_data = {}
        if request.user.is_authenticated:
            initial_data['author'] = _get_display_name(request.user)
        form = ThreadPostForm(initial=initial_data)
    return render(request, "board/link_form.html", {"form": form})

@csrf_exempt
@require_POST
def thread_create_api(request):
    try:
        data = json.loads(request.body)
        form = ThreadPostForm(data)
        
        if 'content' in form.fields:
            form.fields['content'].max_length = 140

        if form.is_valid():
            link = form.save(commit=False)
            link.category = 'thread'
            link.save()
            return JsonResponse({'message': 'success', 'id': link.id}, status=201)
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

def ai_list(request):
    links = InfoPost.objects.filter(category='ai').order_by("-created_at")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.like_count = link.likes.count()
        if request.user.is_authenticated:
            link.is_liked = link.likes.filter(id=request.user.id).exists()
        else:
            link.is_liked = False

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/link_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "board_type": "ai",
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def ai_create(request):
    if request.method == "POST":
        form = InfoPostForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            if request.user.is_authenticated:
                link.author = _get_display_name(request.user)
            link.category = 'ai'
            link.save()
            return redirect("board:ai_list")
    else:
        initial_data = {}
        if request.user.is_authenticated:
            initial_data['author'] = _get_display_name(request.user)
        form = InfoPostForm(initial=initial_data)
    return render(request, "board/link_form.html", {"form": form, "board_type": "ai"})

@csrf_exempt
@require_POST
def ai_create_api(request):
    try:
        data = json.loads(request.body)
        form = InfoPostForm(data)
        if 'content' in form.fields:
            form.fields['content'].max_length = 500

        if form.is_valid():
            link = form.save(commit=False)
            link.category = 'ai'
            link.save()
            return JsonResponse({'message': 'success', 'id': link.id}, status=201)
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

def link_create(request):
    if request.method == "POST":
        form = LinkPostForm(request.POST)
        if form.is_valid():
            link = form.save()
            if link.category == 'best':
                return redirect("board:menu6")
            return redirect("board:link_list")
    else:
        form = LinkPostForm()
    return render(request, "board/link_form.html", {"form": form})


@require_POST
def link_like(request, link_id):
    link = get_object_or_404(LinkPost, id=link_id)
    link.is_recommended = not link.is_recommended
    link.save()
    return JsonResponse({'like_count': 0, 'is_liked': link.is_recommended})

@require_POST
def match_like(request, match_id):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    replace_oldest = bool(payload.get("replace_oldest"))

    with transaction.atomic():
        match = get_object_or_404(SoccerMatch.objects.select_for_update(), id=match_id)

        if match.is_recommended:
            match.is_recommended = False
            match.liked_at = None
            match.save(update_fields=["is_recommended", "liked_at"])
            return JsonResponse({
                'is_liked': False,
                'favorite_count': SoccerMatch.objects.filter(is_recommended=True).count(),
            })

        favorite_matches = (
            SoccerMatch.objects.select_for_update()
            .filter(is_recommended=True)
            .exclude(id=match.id)
            .order_by("liked_at", "id")
        )
        favorite_count = favorite_matches.count()
        if favorite_count >= MAX_FAVORITE_MATCHES and not replace_oldest:
            return JsonResponse({
                'requires_confirmation': True,
                'is_liked': False,
                'message': '즐겨찾기 10게임입니다. 오래된 경기를 삭제할까요?',
            })

        removed_match_id = None
        if favorite_count >= MAX_FAVORITE_MATCHES:
            oldest_match = favorite_matches.first()
            if oldest_match:
                removed_match_id = oldest_match.id
                oldest_match.is_recommended = False
                oldest_match.liked_at = None
                oldest_match.save(update_fields=["is_recommended", "liked_at"])

        match.is_recommended = True
        match.liked_at = timezone.now()
        match.save(update_fields=["is_recommended", "liked_at"])

    return JsonResponse({
        'is_liked': True,
        'removed_match_id': removed_match_id,
        'favorite_count': SoccerMatch.objects.filter(is_recommended=True).count(),
        'match': _match_favorite_payload(match),
    })


@require_POST
def match_bet(request, match_id):
    if not _can_set_match_bet(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        bet = int(payload.get("bet"))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid bet'}, status=400)

    if bet not in MATCH_BET_VALUES:
        return JsonResponse({'error': 'Invalid bet'}, status=400)

    with transaction.atomic():
        match = get_object_or_404(SoccerMatch.objects.select_for_update(), id=match_id)
        if match.result is not None:
            return JsonResponse({
                'error': 'Match already finished',
                'match': _match_bet_payload(match),
            }, status=409)

        if match.bet is not None:
            return JsonResponse({
                'error': 'Bet already set',
                'match': _match_bet_payload(match),
            }, status=409)

        match.bet = bet
        match.save(update_fields=["bet"])

    return JsonResponse({
        'message': 'success',
        'match': _match_bet_payload(match),
    })


@require_POST
def info_like(request, info_id):
    post = get_object_or_404(InfoPost, id=info_id)
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required'}, status=403)
    if post.likes.filter(id=request.user.id).exists():
        post.likes.remove(request.user)
        is_liked = False
    else:
        post.likes.add(request.user)
        is_liked = True
    return JsonResponse({'like_count': post.likes.count(), 'is_liked': is_liked})

def post_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    post.is_recommended = not post.is_recommended
    post.save()
    return redirect(request.META.get("HTTP_REFERER", "board:post_list"))

@login_required
@require_POST
def post_like_json(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.likes.filter(id=request.user.id).exists():
        post.likes.remove(request.user)
        is_liked = False
    else:
        post.likes.add(request.user)
        is_liked = True
    return JsonResponse({'like_count': post.likes.count(), 'is_liked': is_liked})

def popular_list(request):
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    links = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")
    
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    return render(
        request,
        "board/menu_popular.html",
        {"page_obj": page_obj, "query": query},
    )

def menu4(request):
    posts = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")
    query = request.GET.get("q", "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(content__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(posts, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "board/menu4.html",
        {"page_obj": page_obj, "query": query},
    )


@login_required
def menu5(request):
    links = Post.objects.filter(category='secret').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20) # links 변수명을 그대로 사용했지만 실제로는 Post 객체입니다
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for post in page_obj:
        post.like_count = post.likes.count()
        if request.user.is_authenticated:
            post.is_liked = post.likes.filter(id=request.user.id).exists()
        else:
            post.is_liked = False

    recent_popular = (
        Post.objects.filter(category='secret')
        .annotate(like_count=Count('likes'))
        .filter(like_count__gt=0)
        .order_by("-like_count", "-id")[:5]
    )

    return render(
        request,
        "board/menu5.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_popular": recent_popular,
        },
    )

@login_required
def secret_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            images = request.FILES.getlist("images")
            if len(images) > 3:
                form.add_error(None, "이미지는 최대 3장까지 업로드할 수 있습니다.")
            else:
                post = form.save(commit=False)
                post.author = _get_display_name(request.user)
                post.category = 'secret'
                post.save()
                _save_post_images(post, images, 3)
                if hasattr(request.user, "profile"):
                    request.user.profile.points += 10
                    request.user.profile.save()
                return redirect("board:secret_detail", post_id=post.id)
    else:
        form = PostForm()
    return render(
        request,
        "board/post_form.html",
        {"form": form, "remaining_slots": list(range(3))},
    )

@login_required
def secret_detail(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.category != 'secret':
        return redirect("board:post_detail", post_id=post.id)
    
    post.views += 1
    post.save()
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = _get_display_name(request.user)
            comment.save()
            if hasattr(request.user, "profile"):
                request.user.profile.points += 3
                request.user.profile.save()
            return redirect("board:secret_detail", post_id=post.id)
    else:
        form = CommentForm()
    is_author = request.user.is_authenticated and _get_display_name(request.user) == post.author

    previous_post = Post.objects.filter(category=post.category, id__lt=post.id).order_by('-id').first()
    next_post = Post.objects.filter(category=post.category, id__gt=post.id).order_by('id').first()

    return render(
        request,
        "board/post_detail.html",
        {"post": post, "form": form, "is_author": is_author, "previous_post": previous_post, "next_post": next_post},
    )

@login_required
def secret_edit(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if _get_display_name(request.user) != post.author:
        return redirect("board:secret_detail", post_id=post.id)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            images = request.FILES.getlist("images")
            existing_count = post.images.count()
            remaining = max(0, 3 - existing_count)
            if len(images) > remaining:
                form.add_error(
                    None,
                    f"이미지는 최대 3장까지 업로드할 수 있습니다. 현재 {existing_count}장 등록됨.",
                )
            else:
                form.save()
                _save_post_images(post, images, remaining)
                return redirect("board:secret_detail", post_id=post.id)
    else:
        form = PostForm(instance=post)
    remaining = max(0, 3 - post.images.count())
    return render(
        request,
        "board/post_form.html",
        {
            "form": form,
            "is_edit": True,
            "post": post,
            "images": post.images.all(),
            "remaining_slots": list(range(remaining)),
        },
    )

@login_required
def secret_delete(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if _get_display_name(request.user) == post.author and request.method == "POST":
        post.delete()
        return redirect("board:menu5")
    return redirect("board:secret_detail", post_id=post.id)

def menu6(request):
    links = LinkPost.objects.filter(category='best').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/menu6.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def menu7(request):
    links = LinkPost.objects.filter(category='xart').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/menu7.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def menu7_create(request):
    if request.method == "POST":
        data = request.POST.copy()
        data['category'] = 'xart'
        form = LinkPostForm(data)
        if form.is_valid():
            form.save()
            return redirect("board:menu7")
    else:
        form = LinkPostForm(initial={'category': 'xart'})
    return render(request, "board/link_form.html", {"form": form})

@csrf_exempt
@require_POST
def menu7_create_api(request):
    try:
        data = json.loads(request.body)
        data['category'] = 'xart'
        form = LinkPostForm(data)
        if form.is_valid():
            link = form.save()
            return JsonResponse({'message': 'success', 'id': link.id}, status=201)
        else:
            return JsonResponse({'errors': form.errors}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

def menu8(request):
    links = LinkPost.objects.filter(category='movie').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/menu8.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def menu8_create(request):
    if request.method == "POST":
        data = request.POST.copy()
        data['category'] = 'movie'
        form = LinkPostForm(data)
        if form.is_valid():
            form.save()
            return redirect("board:menu8")
    else:
        form = LinkPostForm(initial={'category': 'movie'})
    return render(request, "board/link_form.html", {"form": form})

def menu9(request):
    links = LinkPost.objects.filter(category='itnews').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/menu9.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def menu9_create(request):
    if request.method == "POST":
        data = request.POST.copy()
        data['category'] = 'itnews'
        form = LinkPostForm(data)
        if form.is_valid():
            form.save()
            return redirect("board:menu9")
    else:
        form = LinkPostForm(initial={'category': 'itnews'})
    return render(request, "board/link_form.html", {"form": form})

def menu10(request):
    links = LinkPost.objects.filter(category='stock').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/menu10.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def menu10_create(request):
    if request.method == "POST":
        data = request.POST.copy()
        data['category'] = 'stock'
        form = LinkPostForm(data)
        if form.is_valid():
            form.save()
            return redirect("board:menu10")
    else:
        form = LinkPostForm(initial={'category': 'stock'})
    return render(request, "board/link_form.html", {"form": form})

def menu11(request):
    links = LinkPost.objects.filter(category='ground').order_by("-id")
    query = request.GET.get("q", "").strip()
    if query:
        links = links.filter(
            Q(title__icontains=query)
            | Q(url__icontains=query)
            | Q(author__icontains=query)
        )
    paginator = Paginator(links, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for link in page_obj:
        link.is_liked = link.is_recommended

    recent_recommended = Post.objects.filter(category='common').annotate(like_count=Count('likes')).filter(like_count__gt=0).order_by("-like_count", "-id")[:5]
    target_categories = ['best', 'xart', 'movie', 'itnews', 'ground', 'stock']
    recent_popular = LinkPost.objects.filter(category__in=target_categories, is_recommended=True).order_by("-created_at")[:5]

    return render(
        request,
        "board/menu11.html",
        {
            "page_obj": page_obj,
            "query": query,
            "recent_recommended": recent_recommended,
            "recent_popular": recent_popular,
        },
    )

def menu11_create(request):
    if request.method == "POST":
        data = request.POST.copy()
        data['category'] = 'ground'
        form = LinkPostForm(data)
        if form.is_valid():
            form.save()
            return redirect("board:menu11")
    else:
        form = LinkPostForm(initial={'category': 'ground'})
    return render(request, "board/link_form.html", {"form": form})


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            if hasattr(user, "profile"):
                user.profile.points += 10
                user.profile.save()
            login(request, user)
            return redirect("board:home")
    else:
        form = SignUpForm()
    return render(request, "board/signup.html", {"form": form})


def login_view(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                if hasattr(user, 'profile') and user.profile.is_temporary_password:
                    return redirect("board:password_change")
                if next_url:
                    return redirect(next_url)
                return redirect("board:home")
            else:
                form.add_error(None, "이메일 또는 비밀번호가 올바르지 않습니다.")
    else:
        form = LoginForm()
    return render(request, "board/login.html", {"form": form, "next": next_url})


def logout_view(request):
    logout(request)
    return redirect("board:home")


def password_reset(request):
    temp_password = None
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            nickname = form.cleaned_data['nickname']
            try:
                user = User.objects.get(username=email)
                if user.profile.nickname == nickname:
                    temp_password = get_random_string(10)
                    user.set_password(temp_password)
                    user.save(update_fields=["password"])
                    user.profile.is_temporary_password = True
                    user.profile.save()
                else:
                    form.add_error(None, "이메일 또는 닉네임이 일치하지 않습니다.")
            except User.DoesNotExist:
                form.add_error(None, "이메일 또는 닉네임이 일치하지 않습니다.")
    else:
        form = PasswordResetForm()
    return render(request, "board/password_reset.html", {"form": form, "temp_password": temp_password})


@login_required
def password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password'])
            request.user.save(update_fields=["password"])
            request.user.profile.is_temporary_password = False
            request.user.profile.save()
            login(request, request.user)  # 비밀번호 변경 후 세션 유지
            return redirect("board:profile")
    else:
        form = PasswordChangeForm()
    return render(request, "board/password_change.html", {"form": form})


@login_required
def profile(request):
    display_name = _get_display_name(request.user)
    post_count = Post.objects.filter(author=display_name).count()
    comment_count = Comment.objects.filter(author=display_name).count()
    points = request.user.profile.points if hasattr(request.user, "profile") else 0
    return render(
        request,
        "board/profile.html",
        {
            "post_count": post_count,
            "comment_count": comment_count,
            "points": points,
        },
    )

def match_list(request):
    match_years = [2027, 2026]
    match_leagues = [
        {"label": "프리미어리그", "value": "프리미어리그"},
        {"label": "라리가", "value": "라리가"},
        {"label": "분데스리가", "value": "분데스리가"},
        {"label": "대표팀", "value": "대표"},
    ]
    league_values = [league["value"] for league in match_leagues]
    selected_year = request.GET.get("year")
    try:
        selected_year = int(selected_year)
    except (TypeError, ValueError):
        selected_year = match_years[0]
    if selected_year not in match_years:
        selected_year = match_years[0]

    selected_league = request.GET.get("league")
    if selected_league not in league_values:
        selected_league = league_values[0]

    scheduled_matches = SoccerMatch.objects.filter(
        Q(score__isnull=True) | Q(score=''),
        league=selected_league,
        year=selected_year,
    ).order_by('match_id')
    result_matches = (
        SoccerMatch.objects.filter(
            league=selected_league,
            year=selected_year,
        )
        .exclude(score__isnull=True)
        .exclude(score='')
        .order_by('-match_id')
    )
    schedule_paginator = Paginator(scheduled_matches, 20)
    result_paginator = Paginator(result_matches, 20)
    schedule_page_obj = schedule_paginator.get_page(request.GET.get("schedule_page"))
    result_page_obj = result_paginator.get_page(request.GET.get("result_page"))
    active_tab = request.GET.get("tab")
    if active_tab not in ["schedule", "results"]:
        active_tab = "schedule"
    recent_liked_matches = SoccerMatch.objects.filter(is_recommended=True).order_by("match_date", "id")[:10]
    match_bet_accuracy_stats = _match_bet_accuracy_stats()
    context = {
        'schedule_page_obj': schedule_page_obj,
        'result_page_obj': result_page_obj,
        'recent_liked_matches': recent_liked_matches,
        'can_set_match_bet': _can_set_match_bet(request.user),
        'match_bet_count': match_bet_accuracy_stats['bet_count'],
        'match_bet_accuracy': match_bet_accuracy_stats['accuracy'],
        'active_tab': active_tab,
        'match_years': match_years,
        'selected_year': selected_year,
        'match_leagues': match_leagues,
        'selected_league': selected_league,
    }
    return render(request, 'board/match_list.html', context)
