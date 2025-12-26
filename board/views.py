from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.utils.crypto import get_random_string
from .forms import CommentForm, LinkPostForm, PostForm, SignUpForm, LoginForm, PasswordResetForm, PasswordChangeForm
from .models import Comment, LinkPost, Post, PostImage, Profile


def _get_display_name(user):
    if hasattr(user, "profile"):
        return user.profile.nickname
    return user.get_username()


def _save_post_images(post, images, remaining):
    for image in images[:remaining]:
        PostImage.objects.create(post=post, image=image)


def home(request):
    recent_posts = Post.objects.order_by("-created_at")[:3]
    recent_links = LinkPost.objects.order_by("-created_at")[:3]
    recent_recommended = Post.objects.filter(is_recommended=True).order_by("-created_at")[:3]
    return render(
        request,
        "board/home.html",
        {
            "recent_posts": recent_posts,
            "recent_links": recent_links,
            "recent_recommended": recent_recommended,
        },
    )


def post_list(request):
    posts = Post.objects.order_by("-created_at")
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
        "board/post_list.html",
        {"page_obj": page_obj, "query": query},
    )


@login_required
def post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            images = request.FILES.getlist("images")
            if len(images) > 3:
                form.add_error(None, "이미지는 최대 3장까지 업로드할 수 있습니다.")
            else:
                post = form.save(commit=False)
                post.author = _get_display_name(request.user)
                post.save()
                _save_post_images(post, images, 3)
                if hasattr(request.user, "profile"):
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
    return render(
        request,
        "board/post_detail.html",
        {"post": post, "form": form, "is_author": is_author},
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
        return redirect("board:post_detail", post_id=post.id)
    image = get_object_or_404(PostImage, id=image_id, post=post)
    if request.method == "POST":
        image.delete()
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
    links = LinkPost.objects.filter(category='info').order_by("-created_at")
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
    return render(
        request,
        "board/link_list.html",
        {"page_obj": page_obj, "query": query},
    )


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


def post_like(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    post.is_recommended = not post.is_recommended
    post.save()
    return redirect(request.META.get("HTTP_REFERER", "board:post_list"))


def menu4(request):
    posts = Post.objects.filter(is_recommended=True).order_by("-created_at")
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
    links = LinkPost.objects.order_by("-created_at")
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
    return render(
        request,
        "board/menu5.html",
        {"page_obj": page_obj, "query": query},
    )


def menu6(request):
    links = LinkPost.objects.filter(category='best').order_by("-created_at")
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
    return render(
        request,
        "board/menu6.html",
        {"page_obj": page_obj, "query": query},
    )


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
                    user.save()
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
            request.user.save()
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
