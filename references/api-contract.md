# AI Marketing Publish API Contract

This is the customer-site API consumed by the `aimarketing` project.

## Authentication

Every request uses:

```http
Authorization: Bearer <api_token>
Accept: application/json
Content-Type: application/json
```

Reject missing or invalid tokens before any write action.

## GET /api/ping

Return:

```json
{ "success": true }
```

## GET /api/posts/categories

Return either:

```json
{
  "categories": [
    { "id": "1", "slug": "tin-tuc", "name": "Tin tức" }
  ]
}
```

Or:

```json
[
  { "id": "1", "slug": "tin-tuc", "name": "Tin tức" }
]
```

`id` and `slug` are optional. `name` should be present. If the customer site has no categories, return an empty list.

## POST /api/posts

Create a new post.

Request:

```json
{
  "title": "Tiêu đề",
  "body": "<p>Nội dung HTML</p>",
  "description": "Meta description",
  "faq": [
    { "question": "Q1", "answer": "A1" }
  ],
  "image_urls": [
    "https://cdn.example.com/image.jpg"
  ],
  "category_id": "1",
  "category_slug": "tin-tuc"
}
```

Required: `title`, `body`.

Optional: `description`, `faq`, `image_urls`, `category_id`, `category_slug`.

`image_urls` may contain remote CDN or signed URLs. Customer sites that persist those URLs should allow at least 2048 characters or import the image and store a shorter local path.

Response must include URL:

```json
{ "url": "https://customer-site.com/blog/slug" }
```

## PUT /api/posts

Update an existing post by `published_url`.

Request:

```json
{
  "published_url": "https://customer-site.com/blog/slug",
  "title": "Tiêu đề đã sửa",
  "body": "<p>Nội dung đã sửa</p>",
  "description": "Meta description đã sửa",
  "faq": [],
  "image_urls": [],
  "category_id": "1",
  "category_slug": "tin-tuc"
}
```

Required: `published_url`, `title`, `body`.

Response:

```json
{ "success": true }
```

Or:

```json
{ "url": "https://customer-site.com/blog/new-slug" }
```

If the URL changes, AI Marketing will update `published_url`.

## Errors

Use JSON:

```json
{ "message": "Token không hợp lệ" }
```

Recommended statuses:

- `401`: missing token
- `403`: invalid token
- `404`: post not found for update
- `422`: invalid payload
- `500`: unexpected server error
