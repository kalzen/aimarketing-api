# Images: use the CDN URLs directly (multiple images, formats, long URLs)

## The rule

**Use the image URLs AI Marketing sends exactly as they are. Do not download, re-upload, rename, resize or re-host them.** They are public CDN URLs (CloudFront/S3, `public_embed`): stable, they never expire, and they are already optimised (WebP, compressed). Downloading them adds nothing, costs time inside a 60-second request, and is the main reason publishes time out and create duplicate posts.

Import/re-host is an **opt-in exception** only when the customer explicitly asks to keep images on their own storage, or when the project uses `site_image_delivery=signed_fetch` (expiring URLs, see below). Never make it the default, and never tell the operator the site "downloads the images itself" as if it were required.

## What AI Marketing sends

- `image_urls`: ordered list of absolute `https` URLs (1–3, sometimes more). **First = cover / thumbnail.**
- `body`: HTML whose `<img src>` tags use the same URLs (an image can appear in both places; extra body placeholders may reuse the same URL).
- Default delivery `public_embed`: URLs like `https://xxxx.cloudfront.net/12/generated-<uuid>.webp`. AI Marketing makes the object public-read before sending. Stable, short (<150 chars).
- `signed_fetch` (only when the operator sets `site_image_delivery=signed_fetch`): expiring pre-signed URLs with `X-Amz-*` query strings, **1000+ characters**. These are the only URLs that must be downloaded during the request; never embed them in stored HTML. Tell the operator to switch to `public_embed` instead if the site can use the CDN directly.
- Formats: website post images are **WebP** (`.webp`), older ones `.png`/`.jpg`.
- Updates add `force_replace_images: true` and `replace_images: true`: replace the cover and body images with the new URLs (ignore cached/empty `src`).

## What the site must do

1. **Store every URL in `image_urls` as is**, in order; the first is the cover/thumbnail. Do not keep only the first.
2. **Keep body `<img>` tags with their CDN `src`** (and `alt`, `width`, `height`, `loading`) through sanitising. Allow `figure`/`figcaption`. Strip `script`, `iframe`, inline `on*` handlers. Do not rewrite `src` to a local path.
3. **Never put a URL in a `varchar(255)` column.** Use `text` (or ≥ 2048 chars). A long URL in `thumbnail varchar(255)` produces SQL `Data too long for column 'thumbnail'` → HTTP 500. Validate `image_urls.*` as a string `max:2048` that starts with `http(s)://`.
4. **Allow the CDN host everywhere it can be blocked**: Content-Security-Policy `img-src` (add the CloudFront/S3 host), hotlink-protection rules, image-proxy allow-lists, Next.js `images.remotePatterns` / `<Image>` domains (or `unoptimized`), and any `<img>` URL sanitiser/whitelist in the CMS.
5. **Support WebP in the page**, not in your storage: modern browsers render it from the CDN with no work. Only if you opt in to importing on WordPress < 5.8 do you need the `webp` mime allowance.
6. **Replace on update.** When `force_replace_images` is true, set the cover and body images from the new payload instead of keeping the old ones.
7. If an image cannot be displayed, leave the `<img>` pointing at the CDN URL. Drop an `<img>` only when its `src` is empty or contains `IMAGE_URL`.

### When a stack needs a local file for the cover (e.g. WordPress featured image)

The cover image can still use the CDN URL:

- Store the URL in post meta/field (e.g. `_aimkt_cover_url`) and render it where the theme prints the thumbnail (WordPress: `post_thumbnail_html` and `wp_get_attachment_image_src`/`get_the_post_thumbnail_url` filters, or an existing "external featured image" plugin), **or**
- import **only the cover**, with a ≤ 10 s timeout and fall back to the CDN URL on any failure.

Body images stay as CDN `<img>` tags.

## Opt-in import (only if the customer asks)

If importing is required, do it safely: per-image timeout ≤ 10 s, total budget ≤ 25 s or a background queue, dedupe by URL without the query string, fall back to the remote URL on failure, and never let an import error fail the publish. AI Marketing waits 60 s per attempt and retries 3 times, so a slow synchronous import creates duplicate posts.

## Failure → cause

| Symptom | Cause |
|---|---|
| 500 "Server Error" after create with images | `thumbnail`/image column too short |
| Publish times out, then duplicates | site downloads/re-uploads images synchronously (slower than 60 s × 3 attempts) |
| Only one image on the page | site saved `image_urls[0]` only, or sanitiser removed `<img>` in body |
| Image blank although the URL opens in a browser | CSP `img-src`, hotlink protection or an image-proxy allow-list blocks the CDN host |
| Broken image after a few hours | expiring signed URL embedded in HTML (`signed_fetch`) |
| Images missing after update | site ignored `replace_images`, kept old images |

## Tests to add

- Create with 3 `image_urls` + body `<img>` → all 3 stored, cover set, **URLs unchanged** (CDN host still in the HTML).
- Create with a 1500-char image URL → 2xx, nothing truncated.
- No outbound HTTP request is made to download images during create/update.
- Update with `force_replace_images` → new cover and body images, no leftovers.
