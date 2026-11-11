# WordPress Implementation Pattern

Prefer a small plugin over editing theme files. Kalzen ships a connector, `aimarketing-connector` (in the `aimarketing` repo under `integrations/wordpress/aimarketing-connector`). It already handles Bearer auth (including `REDIRECT_HTTP_AUTHORIZATION`), categories, create, update by `published_url`, localising body images and WebP on old WordPress. Reuse it where possible, but it **does not yet** meet every rule of this skill, so when you install or extend it verify and patch:

- `POST /posts` only creates and `PUT /posts` only updates. AI Marketing updates with POST by default, so set `api_update_method=put` for WordPress projects (or make the POST handler upsert when `published_url` is present).
- It downloads (sideloads) images into the Media Library by default (`import_images` = on, 60 s per download). The CDN URLs are public and permanent, so **turn importing off** (use the CDN directly, see Images below); only the cover needs special handling.
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

- `wp_insert_post` with the content (no image import needed; body `<img>` keep their CDN `src`).
- `post_title` ← `title` (accept ≥ 500 chars), `post_excerpt` ← `description`, status from setting (`publish` default).
- Sanitise `body` with `wp_kses_post` (keeps `img`, headings, tables); wrap bare text blocks in paragraphs with `wpautop` (AI bodies may contain text separated by blank lines).
- Append FAQ as `<h2>` + `<h3>`/`<p>` pairs when `faq` is present.
- **Idempotency:** store a key (`sha1(title + body)`) in post meta; if a post with that key was created in the last 15 minutes return its permalink instead of creating another (AI Marketing retries after timeouts).
- Return `['url' => get_permalink($post_id)]` with status 200/201.

## Images (use the CDN, do not download)

- Keep every body `<img>` exactly as sent (CDN `src`); `wp_kses_post` allows it. Do **not** call `download_url` / `media_handle_sideload` for the body or for `image_urls`. Default the connector's `import_images` setting to **off**.
- Store all `image_urls` in post meta (e.g. `_aimkt_image_urls`, JSON) and the first as `_aimkt_cover_url`.
- Featured image from the CDN without importing: output `_aimkt_cover_url` through the `post_thumbnail_html` filter (and the `get_the_post_thumbnail_url` / `wp_get_attachment_image_src` filters for themes that read the URL), or use an existing "external featured image" plugin. If the theme insists on a real attachment, import **only the cover**: `download_url($url, 10)`, falling back to the CDN URL on failure.
- `.webp` renders from the CDN in every modern browser, so the WordPress < 5.8 mime problem only appears if importing is enabled (then add the `upload_mimes` + `wp_check_filetype_and_ext` fix from the connector's `AIMKT_Media`).
- Allow the CDN host in any CSP / hotlink rule of the site.
- AI Marketing waits 60 s per attempt and retries 3 times: a synchronous import of several images is what produces duplicate posts.

## Update

- Find by `published_url`: post meta `_aimkt_published_url` first, then `url_to_postid($published_url)`; tolerate trailing slash and `http`/`https`. Not found → `404` JSON, never create.
- `wp_update_post`, re-apply content/category/images (replace the cover meta and body images when `force_replace_images` is true), keep the slug.
- Respond `['success' => true, 'url' => get_permalink($post_id)]` with the **same** permalink.

## Tests / validation

Run `scripts/smoke_test_api.py` with the WordPress paths (`--ping-path wp-json/aimarketing/v1/ping --categories-path ... --publish-path ... --update-path ... --update-method put`). Then check in wp-admin that the test post has the featured image, three body images in the Media Library, the category and no duplicate on update; delete the test post.
