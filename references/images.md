# Images: multiple images, formats, long URLs

## What AI Marketing sends

- `image_urls`: ordered list of absolute `https` URLs (1–3, sometimes more). **First = cover / thumbnail.**
- `body`: HTML whose `<img src>` tags use the same URLs (an image can appear in both places; extra body placeholders may reuse the same URL).
- Default delivery `public_embed`: stable public CDN/S3 URLs, e.g. `https://xxxx.cloudfront.net/12/generated-<uuid>.webp`. AI Marketing makes the object public-read before sending. These URLs do not expire and are short (<150 chars).
- `signed_fetch` (only when the operator sets `site_image_delivery=signed_fetch`): expiring pre-signed URLs with `X-Amz-*` query strings, **1000+ characters**. They must be downloaded during the request; never embed them in stored HTML.
- Formats: website post images are **WebP** (`.webp`), older ones `.png`/`.jpg`. Facebook images are JPEG (not sent to websites).
- Updates add `force_replace_images: true` and `replace_images: true`: replace the cover and the body images, ignore cached/empty `src`.

## What the site must do

1. **Store every URL in `image_urls`**, in order. Do not keep only the first. Keep the cover as the thumbnail/featured image.
2. **Keep body `<img>` tags** (`src`, `alt`, `width`, `height`, `loading`) through sanitising. Allow `figure`/`figcaption` too. Strip `script`, `iframe`, inline `on*` handlers.
3. **Never store a URL in a `varchar(255)` column.** Use `text` (or ≥ 2048 chars). A signed URL in `thumbnail varchar(255)` produces SQL `Data too long for column 'thumbnail'` → HTTP 500 right after a 422-free validation. Validate `image_urls.*` as `url|max:2048`.
4. **Hotlink or import — choose one deliberately.**
   - Hotlink (store the URL as is) is fastest and fine for `public_embed`.
   - Import (download into the site's media storage) is required for `signed_fetch` and gives full control, but each download costs time: AI Marketing waits 60 s per attempt and retries up to 3 times. Use a hard per-image timeout (≤ 10 s), a total budget (≤ 25 s) or a background queue, and **fall back to the remote URL** when an import fails. An image failure must never fail the publish.
   - Dedupe imports by source URL without the query string so updates and retries do not download the same image again.
5. **Support WebP.** WordPress < 5.8 or old PHP builds reject `.webp` uploads: allow the `webp` mime for the sideload, or hotlink. Make sure the web server serves `image/webp`.
6. **Never trust the file extension for type**, but do accept `webp|jpg|jpeg|png|gif|avif`.
7. **Replace on update.** When `force_replace_images` is true, re-resolve the cover and body images from the new payload instead of keeping the old attachments.
8. If a body `<img>` URL cannot be fetched/imported, keep the `<img>` pointing at the original URL rather than removing it (a missing image is worse than a slow one). Drop it only when its `src` is empty or contains `IMAGE_URL`.

## Failure → cause

| Symptom | Cause |
|---|---|
| 500 "Server Error" after create with images | `thumbnail`/image column too short, or import exception not caught |
| Publish times out, then duplicates | synchronous image import slower than 60 s × 3 attempts |
| Only one image on the page | site saved `image_urls[0]` only, or sanitiser removed `<img>` in body |
| Broken image after a few hours | expiring signed URL embedded in HTML |
| Upload rejected on WordPress | `.webp` not in allowed mimes (WP < 5.8) |
| Images missing after update | site ignored `replace_images`, kept old attachments |

## Tests to add

- Create with 3 `image_urls` + body `<img>` → all 3 stored/visible, cover set.
- Create with a 1500-char image URL → 2xx, nothing truncated.
- Image import failing (unreachable URL) → post still created, remote URL kept.
- Update with `force_replace_images` → new cover and body images, no leftovers.
