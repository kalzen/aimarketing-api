# Troubleshooting

Read the real server log/exception first. Then find the symptom here. After any fix, rerun `scripts/smoke_test_api.py` (and `--write`).

## Symptom → cause → fix

| Symptom (what AI Marketing shows / what happens) | Likely cause | Fix |
|---|---|---|
| "Invalid token" / 401 / 403 with the right token | Raw vs hash mismatch; config cached; **Authorization header dropped by Apache/CGI/FastCGI** | Compare raw-to-raw or hash-to-hash consistently. Clear config cache. Pass the header through (below) |
| `422` on publish | Validation too strict: `title` max 200, `description` max 255, `image_urls.*` `url` rule failing on odd URLs, `exists:` on category, `faq.*.answer` too short, unknown field rejected | Use the limits in `api-contract.md` (500/500/2000), ignore unknown fields, never validate category with `exists:` |
| `422` then later `{"error":"Server Error"}` / 500 | Validation passed, persistence failed: `Data too long for column 'thumbnail'`, null in NOT NULL column, image import exception | Make image columns `text`; catch image errors and fall back to remote URL; read the SQL exception |
| "Website không trả về URL bài viết" | Response is 2xx without `url` (e.g. `{"success":true}` on create), or HTML/redirect | Return `{"url":"https://…"}` on create; keep API un-redirected |
| Post published but **duplicated** | (a) update sent as POST while site only updates on PUT → creates a new post; (b) publish retried after timeout/failure; (c) create returned a different URL on update | (a) POST with `published_url` must upsert and PUT must work, or set `api_update_method=put`; (b) idempotency guard + answer < 30 s; (c) keep URL stable |
| Update returns a different URL | The site created a new post (see above) or changed slug | Find by `published_url`, update in place, return same URL |
| Publish takes > 60 s, then duplicates | The site downloads/re-uploads the images during the request | Stop downloading: use the CDN URLs directly (`images.md`) |
| Connection reset / `413` on publish | Reverse proxy body limit (nginx `client_max_body_size` default 1 MB, WAF rule) smaller than the post | Raise to ≥ 5 MB for `/api/posts` |
| `405 Method Not Allowed` / HTML instead of JSON | `website_url` redirects (http→https, www, trailing slash): POST became GET | Set `website_url` to the final canonical URL |
| Returned URL contains `/public`, `/project/public`, `localhost`, `http://` | Wrong `APP_URL`, cached routes/config, generated route files (Wayfinder/Ziggy), proxy not trusted | Set production `APP_URL`, clear route/config cache, rebuild assets, trust proxies so URLs are https, grep built files for local fragments |
| Categories are never suggested | Categories endpoint missing/401/empty, or **Đồng bộ danh mục** never pressed | Fix endpoint, press sync in AI Marketing; see `categories.md` |
| Category sent but post lands in default | Site resolves only by integer id, or `category_id` cast to int; or inactive category | Resolve id (string) → slug → default; see `categories.md` |
| Only the cover image shows / images vanish | Site saved only `image_urls[0]`; sanitiser stripped `<img>`; images expired (signed URLs embedded) | See `images.md` |
| WebP upload rejected (WordPress) | The site is importing images and `webp` is not an allowed mime (WP < 5.8) | Do not import: use the CDN URLs directly (or allow `image/webp` for the sideload if importing is required) |
| Image blank though the URL opens in a browser | CSP `img-src`, hotlink protection or image-proxy allow-list blocks the CDN host | Allow the CDN host (`images.md`) |
| Page is one block of text | `body` has bare text blocks separated by blank lines | Wrap bare blocks in `<p>` on save (see stack reference) |
| `{{IMAGE_URL_1}}` visible | Unresolved placeholder reached the site | Drop any `<img>` whose `src` contains `IMAGE_URL`; AI Marketing ≥ commit `1a61ee4` already strips them |

## Authorization header dropped (shared hosting)

Symptom: the token is correct but the app sees no `Authorization` header (always 401), typical on cPanel/Apache with CGI/FastCGI.

Apache `.htaccess` at the web root, before the framework rules:

```apache
RewriteEngine On
RewriteCond %{HTTP:Authorization} .
RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]
```

or `CGIPassAuth On` (Apache ≥ 2.4.13). Laravel reads it through `$request->bearerToken()`; for plain PHP also check `$_SERVER['REDIRECT_HTTP_AUTHORIZATION']`. For nginx + PHP-FPM add `fastcgi_param HTTP_AUTHORIZATION $http_authorization;`.

## Debug order

1. `curl -i` the ping without token, with a wrong token, with the right token.
2. Check there is no redirect (`curl -i` shows 301/302).
3. Run the smoke test; read the failing step.
4. Read the server log for the exact exception of any 500.
5. Check what AI Marketing shows to the user: it prints the first of `message|error|detail|errors`.
