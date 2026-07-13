# Node/Express Implementation Pattern

Use this for Node, Express, NestJS, or similar customer projects.

## Environment

```env
AI_MARKETING_API_TOKEN_HASH=
AI_MARKETING_DEFAULT_AUTHOR_ID=
```

Generate a token:

```js
import crypto from "node:crypto";

const token = `amkt_${crypto.randomBytes(32).toString("hex")}`;
const hash = crypto.createHash("sha256").update(token).digest("hex");
console.log({ token, hash });
```

## Middleware

```js
import crypto from "node:crypto";

export function aiMarketingAuth(req, res, next) {
  const header = req.get("authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  const expectedHash = process.env.AI_MARKETING_API_TOKEN_HASH || "";

  if (!match || !expectedHash) {
    return res.status(401).json({ message: "Missing AI Marketing token" });
  }

  const incomingHash = crypto.createHash("sha256").update(match[1].trim()).digest("hex");
  const ok =
    incomingHash.length === expectedHash.length &&
    crypto.timingSafeEqual(Buffer.from(incomingHash), Buffer.from(expectedHash));

  if (!ok) {
    return res.status(403).json({ message: "Invalid AI Marketing token" });
  }

  return next();
}
```

## Routes

```js
router.get("/api/ping", aiMarketingAuth, (req, res) => {
  res.json({ success: true });
});

router.get("/api/posts/categories", aiMarketingAuth, async (req, res) => {
  const categories = await categoryRepo.list();
  res.json({
    categories: categories.map((category) => ({
      id: String(category.id),
      slug: category.slug,
      name: category.name,
    })),
  });
});

router.post("/api/posts", aiMarketingAuth, async (req, res) => {
  const post = await postRepo.create({
    title: req.body.title,
    body: req.body.body,
    description: req.body.description || "",
    faq: req.body.faq || [],
    imageUrls: req.body.image_urls || [],
    categoryId: req.body.category_id || null,
    categorySlug: req.body.category_slug || null,
  });

  res.json({ url: post.url });
});

router.put("/api/posts", aiMarketingAuth, async (req, res) => {
  const post = await postRepo.findByUrl(req.body.published_url);
  if (!post) {
    return res.status(404).json({ message: "Post not found" });
  }

  const updated = await postRepo.update(post.id, {
    title: req.body.title,
    body: req.body.body,
    description: req.body.description || "",
    faq: req.body.faq || [],
    imageUrls: req.body.image_urls || [],
    categoryId: req.body.category_id || null,
    categorySlug: req.body.category_slug || null,
  });

  res.json({ success: true, url: updated.url });
});
```

Adapt repository calls to the target CMS/database. Keep endpoint behavior the same.
