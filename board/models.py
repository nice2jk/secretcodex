import hashlib
from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

class Post(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=20, default='common')
    created_at = models.DateTimeField(auto_now_add=True)
    views = models.PositiveIntegerField(default=0)
    author = models.CharField(max_length=20, default='익명')
    is_recommended = models.BooleanField(default=False)
    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)

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

class InfoPost(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField(max_length=140)
    author = models.CharField(max_length=20, default='익명')
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name='liked_infoposts', blank=True)

    def __str__(self):
        return self.title

class LinkPost(models.Model):
    CATEGORY_CHOICES = [
        ('best', '베스트야'),
        ('xart', '조공모음'),
        ('movie', '영화소식'),
        ('baseball', '야구소식'),
        ('stock', '주식소문'),
    ]
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default='best', verbose_name='카테고리')
    title = models.CharField(max_length=200)
    url = models.URLField(max_length=500, blank=True, null=True)
    author = models.CharField(max_length=20, default='익명')
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name='liked_links', blank=True)
    is_recommended = models.BooleanField(default=False)
    link_id = models.CharField(max_length=32, blank=True)

    def clean(self):
        if not self.link_id:
            target_str = f"{self.title}{self.url or ''}"
            generated_id = hashlib.md5(target_str.encode('utf-8')).hexdigest()
            if LinkPost.objects.filter(link_id=generated_id).exclude(pk=self.pk).exists():
                raise ValidationError("이미 등록된 링크입니다.")
            self.link_id = generated_id
        super().clean()

    def save(self, *args, **kwargs):
        if not self.link_id:
            target_str = f"{self.title}{self.url or ''}"
            self.link_id = hashlib.md5(target_str.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class SoccerMatch(models.Model):
    match_id = models.CharField(max_length=32, unique=True)
    round_num = models.CharField(max_length=20, null=True, blank=True)
    match_date = models.DateTimeField()
    league = models.CharField(max_length=20)
    home_team = models.CharField(max_length=100)
    away_team = models.CharField(max_length=100)
    home_score = models.PositiveSmallIntegerField(null=True, blank=True)
    away_score = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'soccer_matches'
        ordering = ['match_date']

    def __str__(self):
        return f"{self.home_team} vs {self.away_team}"
