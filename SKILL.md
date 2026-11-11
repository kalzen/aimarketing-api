---
name: aimarketing-api
description: Build, verify and troubleshoot the customer-site API that lets the AI Marketing Laravel app publish posts, update already-published posts, sync categories for AI category suggestion, and receive multiple images per post. Use when adding AI Marketing compatible endpoints (GET /api/ping, GET /api/posts/categories, POST /api/posts, PUT /api/posts) to Laravel, WordPress, Node/Express or any other customer project, when publishing fails (invalid token, 401/403, 422, 500 "Server Error", "Website không trả về URL"), when posts are duplicated after update, when images are missing/broken/too long for a column, when AI-suggested categories are not applied, or when a freshly built gateway must be validated before the customer pastes the URL and token into AI Marketing Site/API settings.
---

# AI Marketing API

Use this skill to add (or repair) the customer-side API that lets `aimarketing` publish SEO articles to another website, **without duplicates, broken images or failed publishes**.

`aimarketing` is the client. It calls the customer site, never the reverse. Everything below is derived from what the client really sends and how it reacts to responses.

## Workflow

1. Identify the stack (Laravel, WordPress, Node/Express, other) and the existing routing/auth/media conventions.
2. Read `references/api-contract.md` (exact payloads, limits, client behaviour). It is the source of truth.
3. Read the topic references that apply:
   - Categories / AI suggestion: `references/categories.md`
   - Images (use the CDN URLs directly, multiple images, WebP, long URLs): `references/images.md`
   - Stack pattern: `references/laravel.md`, `references/wordpress.md`, `references/node-express.md`
4. Generate the token (`scripts/generate_api_token.py`) and store it per "Token" below.
5. Implement the four endpoints following the **Non-negotiable rules**.
6. Validate with `scripts/smoke_test_api.py` (read-only first, then `--write`), fix every FAIL and WARN, then hand over the values in "Output".
7. When troubleshooting a live failure, read the real exception/log first, then match the symptom in `references/troubleshooting.md`. A `422` is payload validation; a later `{ "error": "Server Error" }` usually means validation passed and persistence failed.

## Required endpoints

Use these default paths unless the customer asks for custom ones (then record them in AI Marketing project settings, see the table in `references/api-contract.md`):

- `GET /api/ping` → `{ "success": true }`
- `GET /api/posts/categories` → active categories (feeds the AI category suggestion)
- `POST /api/posts` → create, returns `{ "url": "<absolute url>" }`
- `PUT /api/posts` → update by `published_url`, returns `{ "success": true }` or `{ "url": "<same url>" }`

Every request carries `Authorization: Bearer <api_token>`, `Accept: application/json`, `Content-Type: application/json`.

## Non-negotiable rules (each one is a real production failure)

1. **Create and update are different operations.** `POST /api/posts` always creates. Updating must hit the existing post found by `published_url`. AI Marketing defaults to sending updates with **POST** to the same path (`api_update_method=post`); if the site only updates on PUT, every "update" silently creates a duplicate post with a new slug. Make `POST` with a `published_url` behave as an update (upsert) **and** support `PUT`; if you cannot, tell the user to set `api_update_method=put` for the project.
2. **Update keeps the URL.** Return the same `url` (or just `{ "success": true }`). A different URL makes AI Marketing re-point the post to it and means a new post was created.
3. **Return an absolute production `url` on create** (HTTP 200/201 with JSON). No `url` = AI Marketing treats the publish as failed and retries up to 3 times (60s timeout each) → duplicates. Never leak local paths (`/public`, `/project/public`, `localhost`, `/index.php/`).
4. **Be idempotent and fast.** Answer within ~30s. A slow or failing response is retried with the same payload, so guard against duplicates (same title+body within 15 minutes returns the existing URL). Never 500 because of an image.
5. **Be lenient with validation.** AI Marketing titles reach 500 chars, descriptions 500, FAQ answers 2000. Ignore unknown fields (`force_replace_images`, `replace_images`, future ones). Unknown/missing categories and empty `image_urls` must never block publishing.
6. **Resolve the category** by `category_id` first (a string, may be non-numeric), then `category_slug`, then the site default. This is how the AI-suggested category is applied. Return only usable, active categories from the categories endpoint. See `references/categories.md`.
7. **Use the CDN image URLs as they are — do not download them.** `image_urls` (1–3+, first = cover) and the `<img src>` in `body` are public, non-expiring CDN URLs (WebP). Store and render them directly. Do not re-host, rename or rewrite them, do not fetch them during the request, and do not report that the site "downloads the images itself": that is the main cause of timeouts and duplicate posts. Keep every URL (never `varchar(255)`; use `text`/≥2048), keep the `<img>` tags with `alt`, and allow the CDN host in CSP/hotlink/image-proxy rules. Importing is an opt-in exception (customer request, or `site_image_delivery=signed_fetch`). See `references/images.md`.
8. **Do not redirect the API.** A 301/302 (http→https, www, trailing slash) turns the POST into a GET. The `website_url` configured in AI Marketing must already be the final URL.
9. **Always answer JSON errors** with `message`/`error`/`detail`/`errors` and a correct status (401 missing token, 403 wrong token, 404 post to update not found, 422 payload, 500 only for real crashes). HTML error pages (WAF, framework debug) make the failure unreadable for the user.
10. **Authorization header must reach the app.** Shared hosting (Apache + CGI/FastCGI) often drops it; fix per `references/troubleshooting.md` before debugging anything else.

## Token

Use `scripts/generate_api_token.py` (run from the skill folder: `python scripts/generate_api_token.py`). When implementing inside a customer project also add a native generator (Laravel Artisan `aimarketing:token`, WP-CLI/admin action, npm script). Never hardcode the raw token; keep it in `.env`, options or a secrets manager.

AI Marketing stores and sends the **raw** token. Prefer storing a SHA-256 hash on the site and comparing `hash('sha256', $incoming)`; if the project already uses a raw token (`AI_MARKETING_API_TOKEN`), compare raw to raw with `hash_equals` and do not hash either side. Do not mix raw-token env names with hash comparison logic.

## Validation checklist

Run `python scripts/smoke_test_api.py --base-url <website_url> --token <raw token> [--update-method put]` and then again with `--write` (creates a "[AIMKT TEST]" post that you must delete). Done only when it reports 0 FAIL and 0 WARN. It verifies:

- No redirect on the API; missing/wrong token rejected; valid token passes.
- Categories shape; names present; no duplicates/"Uncategorized".
- Create with 3 images + a 1500-char image URL + unknown category + long title/description + extra fields → 2xx with absolute `url` under 30s, no local path in the URL.
- The page shows all 3 images **with their original CDN URLs** (WARN if the site rewrote or re-hosted them); retry of the same payload does not create a second post.
- Update by `published_url` keeps the same URL and changes the content (no new post).

Also add feature tests in the customer project for the same cases (see the stack reference).

## Output

When finished, report:

- The endpoint base URL (and any custom paths) the customer must set in AI Marketing.
- The raw token (shown once) or where to generate it, and the env/option names holding the token or its hash.
- The AI Marketing project settings required: `website_url`, `api_token`, and when applicable `api_update_method`, `api_*_path`, `site_image_delivery`.
- The smoke-test output (0 FAIL / 0 WARN) and the list of test posts that must be deleted.
- Reminder to press **Đồng bộ danh mục** (sync categories) in AI Marketing Site/API settings after deploy so the AI can start suggesting categories.
