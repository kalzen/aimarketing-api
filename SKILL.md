---
name: aimarketing-api
description: Build customer-site API gateways that allow the AI Marketing Laravel app to publish posts, update already-published posts, sync categories, and generate secure Bearer API tokens. Use when adding compatible endpoints to Laravel, WordPress, Node/Express, or other customer projects for AI Marketing Site/API integration.
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
4. Add token generation before endpoint implementation. Prefer storing a SHA-256 token hash and showing the raw token only once.
5. Implement, validate, and document the exact URL/token the customer must paste into AI Marketing.

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

Never hardcode the raw token in source code. Store it in `.env`, database options, or a secrets manager. Prefer comparing `hash('sha256', $incomingToken)` or equivalent against the stored hash.

## Validation Checklist

- Missing/invalid token returns `401` or `403`.
- `GET /api/ping` returns `{ "success": true }`.
- `GET /api/posts/categories` returns either `{ "categories": [...] }` or a direct array.
- `POST /api/posts` creates a post and returns `{ "url": "..." }`.
- `PUT /api/posts` locates by `published_url`, updates the existing post, and returns `{ "success": true }` or `{ "url": "..." }`.
- Category fields are optional and do not block publishing.
- Error responses use JSON with `message`, `error`, `detail`, or `errors`.
- Add tests or a cURL smoke test for every endpoint.

## Output

When finished, report:

- The endpoint base URL.
- The generated raw token value or where the user can generate it.
- The environment keys or admin setting names used to store the token/hash.
- The cURL commands used to validate the gateway.

