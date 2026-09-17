# SecretCodex App API

Base URL:

```text
https://secret4news.xyz/api/v1/
```

Local development URL:

```text
http://localhost:8000/api/v1/
```

## Auth

Login returns a bearer token. Send it on authenticated requests:

```http
Authorization: Bearer <token>
```

Endpoints:

```text
POST /api/v1/auth/signup/
POST /api/v1/auth/login/
POST /api/v1/auth/logout/
GET  /api/v1/auth/me/
POST /api/v1/auth/password/reset/
POST /api/v1/auth/password/change/
```

Login body:

```json
{
  "email": "user@example.com",
  "password": "password"
}
```

Signup body:

```json
{
  "email": "user@example.com",
  "password": "password",
  "nickname": "닉네임"
}
```

## Home

```text
GET /api/v1/home/
```

Returns recent board posts, thread posts, AI news, recommended posts, popular links, and recent best links.

## Ssul Posts

These endpoints are dedicated to `썰게시판` and always use the `common` post category.

Endpoints:

```text
GET    /api/v1/ssul-posts/?page=1&q=검색어
POST   /api/v1/ssul-posts/
GET    /api/v1/ssul-posts/{id}/
PATCH  /api/v1/ssul-posts/{id}/
DELETE /api/v1/ssul-posts/{id}/
DELETE /api/v1/ssul-posts/{id}/images/{image_id}/
POST   /api/v1/ssul-posts/{id}/like/
GET    /api/v1/ssul-posts/{id}/comments/
POST   /api/v1/ssul-posts/{id}/comments/
```

Create JSON body:

```json
{
  "title": "제목",
  "content": "내용"
}
```

For image upload, send `multipart/form-data` with fields `title`, `content`, and up to three `images` files.

## Posts

Categories:

```text
common
secret
```

Endpoints:

```text
GET    /api/v1/posts/?category=common&page=1&q=검색어
POST   /api/v1/posts/
GET    /api/v1/posts/{id}/
PATCH  /api/v1/posts/{id}/
DELETE /api/v1/posts/{id}/
DELETE /api/v1/posts/{id}/images/{image_id}/
POST   /api/v1/posts/{id}/like/
GET    /api/v1/posts/{id}/comments/
POST   /api/v1/posts/{id}/comments/
DELETE /api/v1/comments/{comment_id}/
```

Create post JSON body:

```json
{
  "category": "common",
  "title": "제목",
  "content": "내용"
}
```

For image upload, send `multipart/form-data` with fields `title`, `content`, `category`, and up to three `images` files.

## Info Posts

Categories:

```text
thread
ai
```

Endpoints:

```text
GET    /api/v1/info-posts/?category=ai&page=1&q=검색어
POST   /api/v1/info-posts/
GET    /api/v1/info-posts/{id}/
PATCH  /api/v1/info-posts/{id}/
DELETE /api/v1/info-posts/{id}/
POST   /api/v1/info-posts/{id}/like/
```

Create body:

```json
{
  "category": "ai",
  "title": "뉴스 제목",
  "content": "뉴스 내용",
  "author": "작성자"
}
```

## Link Posts

Categories:

```text
best
xart
movie
itnews
ground
stock
popular
```

Use `popular` only as a list filter.

Endpoints:

```text
GET    /api/v1/link-posts/?category=best&page=1&q=검색어
POST   /api/v1/link-posts/
GET    /api/v1/link-posts/{id}/
PATCH  /api/v1/link-posts/{id}/
DELETE /api/v1/link-posts/{id}/
POST   /api/v1/link-posts/{id}/recommend/
```

Create body:

```json
{
  "category": "best",
  "title": "링크 제목",
  "url": "https://example.com",
  "author": "작성자"
}
```

## Matches

Endpoints:

```text
GET  /api/v1/matches/?year=2026&league=프리미어리그&tab=schedule
GET  /api/v1/matches/{id}/
POST /api/v1/matches/{id}/favorite/
POST /api/v1/matches/{id}/bet/
```

Tabs:

```text
schedule
results
predictions
favorites
```

Favorite body:

```json
{
  "replace_oldest": false
}
```

Bet body:

```json
{
  "bet": 1
}
```

Bet values:

```text
1 = home win
0 = draw
2 = away win
```

## Pagination

List responses include:

```json
{
  "results": [],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total_pages": 1,
    "total_count": 0,
    "has_next": false,
    "has_previous": false
  }
}
```

`per_page` supports 1 to 50.
