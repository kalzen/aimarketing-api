# Laravel Implementation Pattern

Use for Laravel customer sites. Follow the project's Laravel version and conventions (these snippets target Laravel 11/12). A working reference implementation exists in the Kalzen customer site `tiengtrungv2` (`AiMarketingPostController`, `AiMarketingPostService`, `EnsureAiMarketingToken`); the pattern below fixes its weak spots (strict validation, no upsert, no idempotency).

## Config

```env
AI_MARKETING_API_TOKEN_HASH=
AI_MARKETING_DEFAULT_AUTHOR_ID=
AI_MARKETING_DEFAULT_STATUS=published
AI_MARKETING_DEFAULT_CATEGORY_SLUG=
```

```php
// config/services.php
'ai_marketing' => [
    'token_hash' => env('AI_MARKETING_API_TOKEN_HASH'),
    'token' => env('AI_MARKETING_API_TOKEN'), // only for raw-token projects
    'default_author_id' => env('AI_MARKETING_DEFAULT_AUTHOR_ID'),
    'default_status' => env('AI_MARKETING_DEFAULT_STATUS', 'published'),
    'default_category_slug' => env('AI_MARKETING_DEFAULT_CATEGORY_SLUG'),
],
```

Never call `env()` outside config. Prefer the hash; if the project is already configured with a raw token, compare raw to raw and do not hash either side.

## Token command

```php
$token = 'amkt_'.bin2hex(random_bytes(32));
$hash = hash('sha256', $token); // print the raw token once, store the hash
```

## Middleware (`ai-marketing.token`)

```php
$incoming = $request->bearerToken();
$expectedHash = config('services.ai_marketing.token_hash');

if (! is_string($incoming) || $incoming === '' || ! is_string($expectedHash) || $expectedHash === '') {
    return response()->json(['message' => 'Missing AI Marketing token'], 401);
}
if (! hash_equals($expectedHash, hash('sha256', $incoming))) {
    return response()->json(['message' => 'Invalid AI Marketing token'], 403);
}

return $next($request);
```

Raw-token variant: `hash_equals((string) config('services.ai_marketing.token'), $incoming)`.

Always answer JSON for API errors (`bootstrap/app.php`):

```php
->withExceptions(function (Exceptions $exceptions) {
    $exceptions->shouldRenderJsonWhen(fn ($request) => $request->is('api/*') || $request->expectsJson());
})
```

## Routes (`routes/api.php`)

```php
Route::middleware('ai-marketing.token')->group(function () {
    Route::get('/ping', [AiMarketingPostController::class, 'ping']);
    Route::get('/posts/categories', [AiMarketingPostController::class, 'categories']);
    Route::post('/posts', [AiMarketingPostController::class, 'store']);  // create, or update when published_url is present
    Route::put('/posts', [AiMarketingPostController::class, 'update']);
});
```

If the app already versions its API, mount the same routes under that prefix and give the operator the `api_*_path` values.

## Lenient Form Request

```php
public function rules(): array
{
    return [
        'published_url' => ['nullable', 'string', 'max:2048'],
        'title' => ['required', 'string', 'max:500'],
        'body' => ['required', 'string'],
        'description' => ['nullable', 'string', 'max:1000'],
        'faq' => ['nullable', 'array'],
        'faq.*.question' => ['nullable', 'string', 'max:500'],
        'faq.*.answer' => ['nullable', 'string', 'max:5000'],
        'image_urls' => ['nullable', 'array', 'max:20'],
        'image_urls.*' => ['nullable', 'string', 'max:2048'],
        'category_id' => ['nullable', 'string', 'max:255'],
        'category_slug' => ['nullable', 'string', 'max:255'],
    ];
}
```

Do not add `exists:` for categories and do not reject unknown keys (`force_replace_images`, `replace_images`).

## Migration

```php
$table->text('thumbnail')->nullable()->change();   // never varchar(255)
$table->json('images')->nullable();                // every image_urls entry, in order
$table->string('aimkt_key', 40)->nullable()->index(); // idempotency key
```

## Controller

```php
public function store(PostPayloadRequest $request): JsonResponse
{
    if (filled($request->validated('published_url'))) {
        return $this->update($request); // POST with published_url = update (default AI Marketing update method)
    }

    $post = $this->posts->create($request->validated());

    return response()->json(['url' => $this->posts->publicUrl($post)], 201);
}

public function update(PostPayloadRequest $request): JsonResponse
{
    $post = $this->posts->findByPublishedUrl((string) $request->validated('published_url'));
    if ($post === null) {
        return response()->json(['message' => 'Post not found for published_url'], 404);
    }

    $post = $this->posts->update($post, $request->validated());

    return response()->json(['success' => true, 'url' => $this->posts->publicUrl($post)]);
}
```

For `PUT`, `published_url` must be required: add `Rule::requiredIf(fn () => $this->isMethod('put'))` in the request.

## Service essentials

```php
public function create(array $data): Post
{
    $key = sha1($data['title']."\n".$data['body']);
    $existing = Post::query()->where('aimkt_key', $key)->where('created_at', '>=', now()->subMinutes(15))->first();
    if ($existing !== null) {
        return $existing; // AI Marketing retried; do not create a duplicate
    }

    $images = $this->imageUrls($data);

    return Post::create([
        'title' => $data['title'],
        'slug' => $this->uniqueSlug($data['title']),
        'content' => $this->contentWithFaq($this->normalizeBody($data['body']), $data),
        'excerpt' => $data['description'] ?? null,
        'thumbnail' => $images[0] ?? null,
        'images' => $images,
        'category_id' => $this->resolveCategory($data)?->id,
        'aimkt_key' => $key,
        // status/author from config
    ]);
}

private function imageUrls(array $data): array
{
    return array_values(array_filter(
        (array) ($data['image_urls'] ?? []),
        fn ($url) => is_string($url) && preg_match('#^https?://#i', $url) === 1
    ));
}
```

Update: find by slug from `published_url` (last path segment, tolerate trailing slash/query/scheme/www), update the same row, do not change the slug, only overwrite category/images when provided, keep `aimkt_key` in sync. Return the same public URL.

Category resolution (never throws; mind integer primary keys on Postgres):

```php
private function resolveCategory(array $data): ?Category
{
    $id = $data['category_id'] ?? null;
    if (is_string($id) && $id !== '' && ctype_digit($id)) {
        $category = Category::query()->whereKey((int) $id)->where('is_active', true)->first();
        if ($category !== null) {
            return $category;
        }
    }

    $slug = $data['category_slug'] ?? null;
    if (is_string($slug) && $slug !== '') {
        $category = Category::query()->where('slug', $slug)->where('is_active', true)->first();
        if ($category !== null) {
            return $category;
        }
    }

    $default = config('services.ai_marketing.default_category_slug');

    return filled($default) ? Category::query()->where('slug', $default)->first() : null;
}
```

If categories use non-numeric ids (slug/UUID keys), drop the `ctype_digit` guard and look up by the string id.

Body normalisation (AI bodies can have bare text between headings):

```php
private function normalizeBody(string $body): string
{
    // Chữ trần ngay sau thẻ khối/ảnh (chỉ cách một dòng) cũng tách thành đoạn riêng.
    $body = preg_replace('#(</(?:p|h[1-6]|ul|ol|table|blockquote|figure)>|<img\b[^>]*>)[ \t]*\n(?=\S)#i', "$1\n\n", trim($body)) ?? $body;
    $blocks = preg_split('/\n{2,}/', $body) ?: [];

    return collect($blocks)->map(function (string $block): string {
        $block = trim($block);
        if ($block === '' || preg_match('/^<(p|h[1-6]|ul|ol|table|blockquote|figure|img|div|section)\b/i', $block)) {
            return $block;
        }

        return '<p>'.nl2br($block).'</p>';
    })->filter()->implode("\n");
}
```

Sanitise on output (`img`, `h2-h4`, `table`, `figure` allowed; no scripts/iframes) according to the project's existing HTML policy.

URL generation: set production `APP_URL`, trust proxies so URLs are `https`, and verify the returned URL has no `/public` or local path (see troubleshooting).

## Tests (Pest)

- Invalid/missing token → 403/401; valid → ping `{success:true}`.
- Categories response shape, inactive excluded.
- Create with 3 images + 1500-char URL + unknown category + 400-char title → 201, url returned, all images stored, `thumbnail` is the first.
- Same create twice quickly → same URL, one row.
- `POST` with `published_url` and `PUT` with `published_url` → same row updated, same URL, no new row.
- Update with unknown `published_url` → 404 JSON.
- Category by id, by slug, unknown → attached / attached / default.
