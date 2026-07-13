# Laravel Implementation Pattern

Use this for Laravel customer projects. Follow the customer's existing Laravel version and conventions.

## Config

Add environment keys:

```env
AI_MARKETING_API_TOKEN_HASH=
AI_MARKETING_DEFAULT_AUTHOR_ID=
AI_MARKETING_DEFAULT_STATUS=publish
```

Prefer `AI_MARKETING_API_TOKEN_HASH` over storing the raw token.

## Token Command

Create an Artisan command such as `aimarketing:token`.

Behavior:

1. Generate a random token with at least 32 bytes of entropy.
2. Print the raw token once.
3. Print `hash('sha256', $token)`.
4. Optionally write the hash to `.env` only if the project already has a safe local env writer pattern.

PHP token generation:

```php
$token = 'amkt_'.bin2hex(random_bytes(32));
$hash = hash('sha256', $token);
```

## Middleware

Validate Bearer token:

```php
$incoming = $request->bearerToken();
$expectedHash = config('services.ai_marketing.token_hash');

if (! is_string($incoming) || $incoming === '' || ! is_string($expectedHash) || $expectedHash === '') {
    return response()->json(['message' => 'Missing AI Marketing token'], 401);
}

if (! hash_equals($expectedHash, hash('sha256', $incoming))) {
    return response()->json(['message' => 'Invalid AI Marketing token'], 403);
}
```

Do not call `env()` outside config files.

## Routes

Prefer routes in `routes/api.php`:

```php
Route::middleware('ai-marketing.token')->group(function () {
    Route::get('/ping', [AiMarketingPostApiController::class, 'ping']);
    Route::get('/posts/categories', [AiMarketingPostApiController::class, 'categories']);
    Route::post('/posts', [AiMarketingPostApiController::class, 'store']);
    Route::put('/posts', [AiMarketingPostApiController::class, 'update']);
});
```

If the customer app already uses API versioning, put the routes under its existing prefix and tell the AI Marketing user to configure custom paths.

## Controller Behavior

`store`:

- Validate `title` and `body`.
- Resolve category by `category_id` first, then `category_slug`.
- Create post with HTML body.
- Attach or import images only if the app has an existing media flow. Otherwise store `image_urls` as meta.
- Return absolute URL.

`update`:

- Validate `published_url`, `title`, `body`.
- Find post by current permalink/slug/canonical URL mapping.
- Update the same post, not create a new one.
- Return `{ "success": true }` or the new URL.

## Tests

Add feature tests for:

- Invalid token rejected.
- Ping works with valid token.
- Categories response shape.
- Store returns URL.
- Update by `published_url` updates the same post.
