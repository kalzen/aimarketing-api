# Categories and AI category suggestion

## How AI Marketing uses categories

1. The operator presses **Đồng bộ danh mục** in Site/API settings. AI Marketing calls `GET {website_url}/{api_categories_path}` (20 s timeout) and caches the normalised list in the project.
2. When a post is about to be published, AI Marketing asks its AI to choose **one** category from the cached list. The AI sees, per category: **name**, `id`, `slug` (it does not see descriptions or parents). It answers with a list index.
3. The chosen category is sent with the post as `category_id` (always a **string**) and `category_slug`. The same pair is reused on updates.
4. If the sync failed, the list is empty, or the AI cannot pick, the post is published **without** category fields. That must still work.

Consequences for the site:

- The AI can only pick what the categories endpoint returns, and judges only by name/slug. Return clear, topic-specific Vietnamese/English names ("Học HSK", not "Mục 2").
- Without a successful sync (or with an empty list) there is no AI suggestion at all. After deploying, press **Đồng bộ danh mục** once, and again whenever categories change.

## GET /api/posts/categories

Return only categories that posts can be published into: active/visible, leaf or selectable, no "Uncategorized"/"Chưa phân loại" placeholders, no taxonomies of other post types. Keep the list reasonably short (under ~100): the whole list goes into the AI prompt.

```json
{
  "categories": [
    { "id": "3", "slug": "kien-thuc-seo", "name": "Kiến thức SEO" },
    { "id": "7", "slug": "hoc-hsk", "name": "Học HSK" }
  ]
}
```

Rules AI Marketing applies when reading it (`name|title|label`, `id|category_id`, `slug`):

- `name` should always be present. If missing it derives one from `slug`; items with neither are dropped.
- `id` and `slug` are optional but **at least one must be usable** for the site to resolve the category later. Prefer sending both.
- Ids are converted to strings; they do not have to be numeric.
- Entries are de-duplicated by `id|slug|name`; names are cut to 255 chars.
- Empty list `[]` is valid (no categories).
- Hierarchical sites: send the selectable categories flat; put the path in the name ("Tin tức › Sự kiện") when a child name alone is ambiguous.

## Resolving on create/update

Resolve in this order and **never fail the request** because of a category:

1. `category_id` (string) → look up by id.
2. else `category_slug` → look up by slug.
3. else/not found → the site's default category (or no category).

Notes:

- Treat `category_id` as an opaque string. Casting it to int breaks sites whose ids are slugs or UUIDs.
- Validation for these fields is `nullable|string|max:255`. Do not use `exists:` rules (an unknown category would 422 the publish).
- On update, apply the category only when one is sent; do not clear an existing category when none is sent.
- Multi-category taxonomies: assign the one resolved category (AI Marketing sends one).

## Tests to add in the customer project

- Categories endpoint shape and that inactive categories are excluded.
- Create with valid `category_id` → attached; with only `category_slug` → attached; with unknown id+slug → created with default/no category, still 2xx.
- Update does not remove the category when the payload has none.
