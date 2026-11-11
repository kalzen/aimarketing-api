# Node/Express Implementation Pattern

Use for Node, Express, NestJS or similar customer projects. Follow the project's ORM/CMS; the behaviour is what matters (see `api-contract.md`).

## Environment

```env
AI_MARKETING_API_TOKEN_HASH=
AI_MARKETING_DEFAULT_AUTHOR_ID=
AI_MARKETING_DEFAULT_CATEGORY_SLUG=
```

```js
import crypto from "node:crypto";

const token = `amkt_${crypto.randomBytes(32).toString("hex")}`;
const hash = crypto.createHash("sha256").update(token).digest("hex");
console.log({ token, hash }); // show token once, store hash
```

## Middleware

```js
import crypto from "node:crypto";

export function aiMarketingAuth(req, res, next) {
  const match = (req.get("authorization") || "").match(/^Bearer\s+(.+)$/i);
  const expectedHash = process.env.AI_MARKETING_API_TOKEN_HASH || "";

  if (!match || !expectedHash) {
    return res.status(401).json({ message: "Missing AI Marketing token" });
  }

  const incomingHash = crypto.createHash("sha256").update(match[1].trim()).digest("hex");
  const ok =
    incomingHash.length === expectedHash.length &&
    crypto.timingSafeEqual(Buffer.from(incomingHash), Buffer.from(expectedHash));

  return ok ? next() : res.status(403).json({ message: "Invalid AI Marketing token" });
}
```

Behind a proxy set `app.set("trust proxy", true)` so generated URLs are `https`, and raise the JSON body limit: `app.use(express.json({ limit: "5mb" }))` (the default 100 KB rejects normal posts). Always answer JSON errors (final error handler returning `{ message }`).

## Routes

```js
const router = express.Router();

router.get("/api/ping", aiMarketingAuth, (req, res) => res.json({ success: true }));

router.get("/api/posts/categories", aiMarketingAuth, async (req, res) => {
  const categories = await categoryRepo.listActive(); // exclude placeholders like "Uncategorized"
  res.json({
    categories: categories.map((c) => ({ id: String(c.id), slug: c.slug, name: c.name })),
  });
});

async function createPost(req, res) {
  if (req.body?.published_url) return updatePost(req, res); // POST with published_url = update (default AI Marketing method)

  const input = normalise(req.body);
  if (!input.title || !input.body) return res.status(422).json({ message: "title and body are required" });

  const key = crypto.createHash("sha1").update(`${input.title}\n${input.body}`).digest("hex");
  const recent = await postRepo.findRecentByKey(key, 15 * 60 * 1000);
  if (recent) return res.status(200).json({ url: recent.url }); // retry from AI Marketing

  const category = await resolveCategory(input);
  const post = await postRepo.create({ ...input, key, categoryId: category?.id ?? null });
  return res.status(201).json({ url: post.url });
}

async function updatePost(req, res) {
  const input = normalise(req.body);
  const post = await postRepo.findByPublishedUrl(req.body.published_url);
  if (!post) return res.status(404).json({ message: "Post not found for published_url" });

  const updated = await postRepo.update(post.id, input); // same row, same slug
  return res.json({ success: true, url: updated.url });
}

router.post("/api/posts", aiMarketingAuth, createPost);
router.put("/api/posts", aiMarketingAuth, updatePost);
```

## Helpers

```js
function normalise(body = {}) {
  return {
    title: String(body.title || "").slice(0, 500),
    body: String(body.body || ""),                       // wrap bare text blocks in <p> before saving
    description: body.description ? String(body.description) : "",
    faq: Array.isArray(body.faq) ? body.faq : [],
    imageUrls: (Array.isArray(body.image_urls) ? body.image_urls : [])
      .filter((u) => typeof u === "string" && /^https?:\/\//i.test(u)), // keep ALL, any length (text column)
    categoryId: body.category_id != null ? String(body.category_id) : null,
    categorySlug: body.category_slug || null,
  };
}

async function resolveCategory({ categoryId, categorySlug }) {
  return (
    (categoryId && (await categoryRepo.findActiveById(categoryId))) ||
    (categorySlug && (await categoryRepo.findActiveBySlug(categorySlug))) ||
    (process.env.AI_MARKETING_DEFAULT_CATEGORY_SLUG &&
      (await categoryRepo.findActiveBySlug(process.env.AI_MARKETING_DEFAULT_CATEGORY_SLUG))) ||
    null
  ); // never throw for an unknown category
}
```

Store `imageUrls` in a `text`/`jsonb` column, the first one as thumbnail. Never use `varchar(255)`. Do not download the images: store and render the CDN URLs as they are (see `images.md`). In Next.js add the CDN host to `images.remotePatterns` (or use `unoptimized`).

## Tests

Cover: token cases, categories shape, create with 3 images + 1500-char URL + unknown category + 400-char title (2xx, `url` present), duplicate create returns same URL, `POST`/`PUT` with `published_url` update the same record, 404 for unknown `published_url`. Then run `scripts/smoke_test_api.py` against the deployed URL.
