from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    views = models.PositiveIntegerField(default=0)
    author = models.CharField(max_length=20, default='익명')
    is_recommended = models.BooleanField(default=False)

    def __str__(self):
        return self.title

class PostImage(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='post_images/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.post_id} image"

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=20, unique=True)
    is_temporary_password = models.BooleanField(default=False)
    points = models.IntegerField(default=0)

    def __str__(self):
        return self.nickname

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.CharField(max_length=20, default='익명')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.content[:20]

class LinkPost(models.Model):
    CATEGORY_CHOICES = [
        ('info', '정보'),
        ('best', '베스트야'),
        ('xart', '조공모음'),
        ('soccer', '축구소식'),
        ('baseball', '야구소식'),
        ('stock', '주식소문'),
    ]
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='info', verbose_name='카테고리')
    title = models.CharField(max_length=200)
    url = models.URLField()
    author = models.CharField(max_length=20, default='익명')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
