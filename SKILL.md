---
name: aimarketing-api
description: Build and troubleshoot customer-site API gateways that allow the AI Marketing Laravel app to publish posts, update already-published posts, sync categories, generate or verify Bearer API tokens, and diagnose publish failures. Use when adding compatible endpoints to Laravel, WordPress, Node/Express, or other customer projects for AI Marketing Site/API integration, including invalid token errors, 422 validation responses, 500 server errors after publish, image URL/thumbnail storage issues, and production URL/base-path leaks.
---

# AI Marketing API

Use this skill to add the customer-side API that lets `aimarketing` publish SEO articles to another website.

## Workflow

1. Identify the target framework and routing/auth conventions.
2. Read `references/api-contract.md` for the required endpoint contract.
3. Read the framework reference when relevant:
   - Laravel: `references/laravel.md`
   - WordPress: `references/wordpress.md`
   - Node/Express: `references/node-express.md`
4. Add or verify token generation before endpoint implementation. Prefer storing a SHA-256 token hash for new integrations, but match the existing AI Marketing/customer-site contract exactly when it already uses a raw token.
5. Implement, validate, and document the exact URL/token the customer must paste into AI Marketing.
6. For troubleshooting, inspect the real exception/log before changing validation. A `422` is payload validation; a later `{ "error": "Server Error" }` often means the payload passed validation and failed in the persistence layer.

## Required Endpoints

Implement these default paths unless the user explicitly asks for custom paths:

- `GET /api/ping`
- `GET /api/posts/categories`
- `POST /api/posts`
- `PUT /api/posts`

All endpoints must require:

```http
Authorization: Bearer <api_token>
Accept: application/json
Content-Type: application/json
```

## Token Generation

Use `scripts/generate_api_token.py` for a portable token:

```bash
python skills/aimarketing-publish-api-gateway/scripts/generate_api_token.py
```

When implementing inside a customer project, add a native token generator too:

- Laravel: an Artisan command such as `php artisan aimarketing:token`.
- WordPress: a WP-CLI command or admin-only token generation action.
- Node/Express: an npm script or CLI script.

Never hardcode the raw token in source code. Store it in `.env`, database options, or a secrets manager.

For new integrations, prefer comparing `hash('sha256', $incomingToken)` or equivalent against the stored hash. If the existing AI Marketing app and customer site are configured for a raw token such as `AI_MARKETING_API_TOKEN`, compare the Bearer token directly with `hash_equals($expectedToken, $incomingToken)` and do not hash either side. Do not mix raw-token env names with hash comparison logic.

## Validation Checklist

- Missing/invalid token returns `401` or `403`.
- `GET /api/ping` returns `{ "success": true }`.
- `GET /api/posts/categories` returns either `{ "categories": [...] }` or a direct array.
- `POST /api/posts` creates a post and returns `{ "url": "..." }`.
- `PUT /api/posts` locates by `published_url`, updates the existing post, and returns `{ "success": true }` or `{ "url": "..." }`.
- Category fields are optional and do not block publishing.
- Image URLs longer than 255 characters publish successfully or are handled intentionally; do not store remote CDN/signed URLs in a `varchar(255)` thumbnail column.
- Returned URLs use the production root domain and do not include local paths such as `/project/public`, `/aimarketing/public`, or `/tiengtrungv2/public`.
- Error responses use JSON with `message`, `error`, `detail`, or `errors`.
- Add tests or a cURL smoke test for every endpoint.

## Troubleshooting Notes

- **Invalid AI Marketing token**: verify whether both apps use raw token or token hash. Check config keys, cached config, and middleware comparison logic. A raw token must not be hashed before comparison.
- **`422` followed by `Server Error` on publish**: inspect the server exception. If SQL reports `Data too long for column 'thumbnail'`, change the target column to `text` or store only a bounded local media path. Keep request validation and database column lengths aligned.
- **Production links contain local subdirectory paths**: for Laravel/Inertia/Wayfinder sites, generated route files and bundles can bake in `APP_URL`. Clear route/config cache, generate routes with the production root URL, rebuild assets, then grep generated artifacts for unwanted local path fragments.

## Output

When finished, report:

- The endpoint base URL.
- The generated raw token value or where the user can generate it.
- The environment keys or admin setting names used to store the token/hash.
- The cURL commands used to validate the gateway.

