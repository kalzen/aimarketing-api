# AI Marketing Publish API Contract

This is the customer-site API consumed by the `aimarketing` Laravel app. The client behaviour below was read from its source (`SitePublishService`, `SitePostCategoryService`, `S3MediaUrl`), not guessed.

## Client behaviour you must design for

| Behaviour | Value |
|---|---|
| HTTP timeout per publish/update attempt | 60 s (`SITE_PUBLISH_TIMEOUT_SECONDS`) |
| Attempts per publish/update | 3 (`SITE_PUBLISH_MAX_RETRIES`), same payload every time |
| What counts as a failed attempt | non-2xx, network error/timeout, **or a 2xx without `url`** (create) / without `success:true` or `url` (update) |
| Redirects | followed by the HTTP client; a 301/302 turns POST into GET → fails |
| Categories sync timeout | 20 s, GET |
| `published_url` stored | truncated to 500 chars |
| `website_url` in production | must be a public host (localhost/private IPs are rejected by AI Marketing) |

Because a failed-looking response is retried with an identical payload, **create must be idempotent** (see "Idempotency").

## AI Marketing project settings (Site/API)

| Setting | Default | Meaning |
|---|---|---|
| `website_url` | — | Base URL, final canonical https URL (no redirect) |
| `api_token` | — | Raw Bearer token |
| `api_test_path` | `api/ping` | Health check |
| `api_categories_path` | `api/posts/categories` | Categories sync |
| `api_publish_path` | `api/posts` | Create |
| `api_update_path` | `api/posts` | Update |
| `api_update_method` | `post` | `post` or `put`: HTTP method used to update |
| `site_image_delivery` | `public_embed` | `public_embed` (stable public image URLs) or `signed_fetch` (expiring signed URLs, site must download them during the request) |

These keys live in the project `settings` JSON (set by the AI Marketing operator). WordPress and other custom-path sites need `api_*_path` overrides.

## Authentication

Every request:

```http
Authorization: Bearer <api_token>
Accept: application/json
Content-Type: application/json
```

Reject missing (`401`) or invalid (`403`) tokens before any read of the body or any write. Return JSON.

## GET /api/ping

```json
{ "success": true }
```

## GET /api/posts/categories

Either shape is accepted:

```json
{ "categories": [ { "id": "1", "slug": "tin-tuc", "name": "Tin tức" } ] }
```

```json
[ { "id": "1", "slug": "tin-tuc", "name": "Tin tức" } ]
```

Details and AI behaviour: `categories.md`.

## POST /api/posts (create)

Exactly what AI Marketing sends:

```json
{
  "title": "Tiêu đề bài viết",
  "body": "<p>Mở bài…</p>\n<img src=\"https://cdn.example.com/12/generated-uuid.webp\" alt=\"…\" />\n<h2>…</h2>…",
  "description": "Meta description",
  "faq": [ { "question": "Câu hỏi?", "answer": "Trả lời." } ],
  "image_urls": [
    "https://cdn.example.com/12/generated-uuid-1.webp",
    "https://cdn.example.com/12/generated-uuid-2.webp"
  ],
  "category_id": "3",
  "category_slug": "kien-thuc-seo"
}
```

- Required: `title`, `body`. Everything else optional; `category_*` only present when AI picked one.
- `title` up to **500** chars, `description` up to **500**, `faq[].question` up to 500, `faq[].answer` up to **2000**. Do not reject (or truncate) shorter limits like 200.
- `body` is HTML produced by AI: `h2/h3/h4`, `p`, `ul/ol/li`, `strong/em`, `a`, `table`, `blockquote`, `img`. Paragraphs are **not guaranteed to be wrapped in `<p>`**: bare text blocks separated by blank lines occur next to headings. Normalise on save (wrap bare blocks in `<p>`, or `nl2br`/`wpautop` equivalent) or the page renders as one wall of text.
- Unresolved image placeholders (`{{IMAGE_URL_1}}`) are stripped by AI Marketing before sending. A defensive site may also drop any `<img>` whose `src` contains `IMAGE_URL`.
- `image_urls`: 1 to 3 (sometimes more) absolute https public CDN URLs, first one is the cover. The same URLs are inside `body` as `<img src>`. **Use them directly; do not download or re-host them.** Full rules: `images.md`.
- Unknown extra fields may appear (e.g. `force_replace_images`). Ignore them.

Response (HTTP 200 or 201):

```json
{ "url": "https://customer-site.com/blog/slug" }
```

## Update an already-published post

AI Marketing calls `{api_update_method}` on `{api_update_path}` (default `POST /api/posts`) with the create payload plus:

```json
{
  "published_url": "https://customer-site.com/blog/slug",
  "force_replace_images": true,
  "replace_images": true
}
```

- Locate the post by `published_url`: parse the path, take the last segment (slug) or match a stored permalink; tolerate trailing slash, `http`/`https`, `www`, and query strings. Keep a stored mapping (meta/column) so lookup survives slug changes.
- Update **that** post: title, body, description, FAQ, category, images (replace the cover and body images when `force_replace_images`).
- Not found → `404` JSON (never create a new post on update).
- Respond `{ "success": true }` and/or `{ "url": "<same url>" }` (200). Returning a different `url` makes AI Marketing re-point `published_url`; do that only if the slug truly changed.
- **Both** `PUT /api/posts` and `POST /api/posts` with `published_url` must work (upsert): the default update method is POST on the same path as create.

## Idempotency (required for create)

AI Marketing retries a failed-looking attempt with the same payload. Guard in the create endpoint:

1. Compute `key = sha1(title + "\n" + body)`.
2. If a post with that key was created within the last 15 minutes, return its existing `url` (HTTP 200) instead of creating another.
3. Otherwise create and store the key.

## Errors

JSON only:

```json
{ "message": "Token không hợp lệ" }
```

AI Marketing reads `message`, `error`, `detail`, then flattens `errors` (Laravel validation format). Statuses: `401` missing token, `403` invalid token, `404` post not found on update, `422` invalid payload, `500` unexpected. HTML error pages are shown to the user as raw text.

## Quick cURL checks

```bash
curl -i https://customer-site.com/api/ping -H "Authorization: Bearer TOKEN" -H "Accept: application/json"

curl -i -X POST https://customer-site.com/api/posts \
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"title":"Demo","body":"<p>Nội dung</p>","image_urls":["https://cdn.example.com/a.webp","https://cdn.example.com/b.jpg"],"category_slug":"tin-tuc"}'

curl -i -X PUT https://customer-site.com/api/posts \
  -H "Authorization: Bearer TOKEN" -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"published_url":"https://customer-site.com/blog/demo","title":"Demo sửa","body":"<p>Đã sửa</p>","force_replace_images":true}'
```

Prefer `scripts/smoke_test_api.py`, which runs all of these plus the failure cases.
