# WordPress Implementation Pattern

Prefer a small plugin over editing theme files. Kalzen ships a connector, `aimarketing-connector` (in the `aimarketing` repo under `integrations/wordpress/aimarketing-connector`). It already handles Bearer auth (including `REDIRECT_HTTP_AUTHORIZATION`), categories, create, update by `published_url`, localising body images and WebP on old WordPress. Reuse it where possible, but it **does not yet** meet every rule of this skill, so when you install or extend it verify and patch:

- `POST /posts` only creates and `PUT /posts` only updates. AI Marketing updates with POST by default, so set `api_update_method=put` for WordPress projects (or make the POST handler upsert when `published_url` is present).
- Only the **first** `image_urls` entry is sideloaded (body `<img>` tags are all localised) and each download allows 60 s: add the per-image/total time budget below.
- No create idempotency key: add it (below) so AI Marketing retries do not duplicate posts.

If you build your own, keep to the behaviour described here.

## Storage and authentication

Store the SHA-256 token hash in an option, show the raw token once:

```php
update_option('aimarketing_api_token_hash', hash('sha256', $token), false);
```

```php
function aimarketing_auth(WP_REST_Request $request) {
    $header = $request->get_header('authorization');
    if (! $header && ! empty($_SERVER['REDIRECT_HTTP_AUTHORIZATION'])) {
        $header = $_SERVER['REDIRECT_HTTP_AUTHORIZATION']; // FastCGI/CGI hosting drops the normal header
    }
    if (! preg_match('/Bearer\s+(.+)/i', (string) $header, $matches)) {
        return new WP_Error('aimarketing_missing_token', 'Missing token', ['status' => 401]);
    }

    $expected = get_option('aimarketing_api_token_hash');
    if (! is_string($expected) || $expected === '') {
        return new WP_Error('aimarketing_not_configured', 'Token is not configured', ['status' => 401]);
    }

    if (! hash_equals($expected, hash('sha256', trim($matches[1])))) {
        return new WP_Error('aimarketing_invalid_token', 'Invalid token', ['status' => 403]);
    }

    return true;
}
```

If the header never arrives, add the `.htaccess` rule in `troubleshooting.md`.

## Routes and AI Marketing paths

Register `ping`, `posts/categories`, and the posts route for **both `POST` and `PUT`** (`'methods' => ['POST', 'PUT']` or two registrations) under `aimarketing/v1`. Then the operator sets in AI Marketing project settings:

- `api_test_path`: `wp-json/aimarketing/v1/ping`
- `api_categories_path`: `wp-json/aimarketing/v1/posts/categories`
- `api_publish_path`: `wp-json/aimarketing/v1/posts`
- `api_update_path`: `wp-json/aimarketing/v1/posts`
- `api_update_method`: `put` (if the handler for POST does not upsert on `published_url`)

Pretty permalinks off → use `?rest_route=/aimarketing/v1/posts` as the path. Make sure `website_url` is the final URL (no http→https or www redirect), otherwise the POST becomes a GET.

## Categories

`posts/categories` returns active `category` terms excluding "Uncategorized": `{ "categories": [ { "id": "12", "slug": "hoc-hsk", "name": "Học HSK" } ] }` (use `get_terms(['taxonomy' => 'category', 'hide_empty' => false])`). Resolve on save: `get_term_by('id', (int) $category_id, 'category')` (only when numeric) → `get_term_by('slug', ...)` → default category setting → none. Never fail on an unknown category.

## Create

- `wp_insert_post` with empty content first, then write content once `post_id` exists so imported images attach to the post.
- `post_title` ← `title` (accept ≥ 500 chars), `post_excerpt` ← `description`, status from setting (`publish` default).
- Sanitise `body` with `wp_kses_post` (keeps `img`, headings, tables); wrap bare text blocks in paragraphs with `wpautop` (AI bodies may contain text separated by blank lines).
- Append FAQ as `<h2>` + `<h3>`/`<p>` pairs when `faq` is present.
- **Idempotency:** store a key (`sha1(title + body)`) in post meta; if a post with that key was created in the last 15 minutes return its permalink instead of creating another (AI Marketing retries after timeouts).
- Return `['url' => get_permalink($post_id)]` with status 200/201.

## Images (multiple, WebP, time budget)

- Process **all** `image_urls` and body `<img>` tags: sideload each to the Media Library, first image becomes the featured image, body `src` are rewritten to the local attachment URLs.
- WordPress < 5.8 rejects `.webp`: add `upload_mimes` and a `wp_check_filetype_and_ext` fix just for the sideload (see the connector's `AIMKT_Media`).
- Each download: `download_url($url, 10)` (not 60), total budget ≈ 25 s for the whole request; if the budget is exceeded or a download fails, keep the original remote URL in the body and continue. AI Marketing waits 60 s per attempt and retries 3 times, so a slow synchronous import produces duplicate posts. For many large images, schedule the import with `wp_schedule_single_event` and return immediately.
- Skip re-downloading images already imported (post meta `_aimkt_source_url` = URL without query string).

## Update

- Find by `published_url`: post meta `_aimkt_published_url` first, then `url_to_postid($published_url)`; tolerate trailing slash and `http`/`https`. Not found → `404` JSON, never create.
- `wp_update_post`, re-apply content/category/images (replace the featured image and body images when `force_replace_images` is true), keep the slug.
- Respond `['success' => true, 'url' => get_permalink($post_id)]` with the **same** permalink.

## Tests / validation

Run `scripts/smoke_test_api.py` with the WordPress paths (`--ping-path wp-json/aimarketing/v1/ping --categories-path ... --publish-path ... --update-path ... --update-method put`). Then check in wp-admin that the test post has the featured image, three body images in the Media Library, the category and no duplicate on update; delete the test post.
