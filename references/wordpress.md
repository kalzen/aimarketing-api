# WordPress Implementation Pattern

Use this for WordPress customer sites. Prefer a small plugin over editing theme files.

## Storage

Store the SHA-256 token hash in an option:

```php
update_option('aimarketing_api_token_hash', hash('sha256', $token), false);
```

Show the raw token only once when generated.

## REST Routes

Register routes:

```php
add_action('rest_api_init', function () {
    register_rest_route('aimarketing/v1', '/ping', [
        'methods' => 'GET',
        'callback' => 'aimarketing_ping',
        'permission_callback' => 'aimarketing_auth',
    ]);

    register_rest_route('aimarketing/v1', '/posts/categories', [
        'methods' => 'GET',
        'callback' => 'aimarketing_categories',
        'permission_callback' => 'aimarketing_auth',
    ]);

    register_rest_route('aimarketing/v1', '/posts', [
        'methods' => 'POST',
        'callback' => 'aimarketing_store_post',
        'permission_callback' => 'aimarketing_auth',
    ]);

    register_rest_route('aimarketing/v1', '/posts', [
        'methods' => 'PUT',
        'callback' => 'aimarketing_update_post',
        'permission_callback' => 'aimarketing_auth',
    ]);
});
```

Then configure AI Marketing custom paths:

- `api_test_path`: `wp-json/aimarketing/v1/ping`
- `api_categories_path`: `wp-json/aimarketing/v1/posts/categories`
- `api_publish_path`: `wp-json/aimarketing/v1/posts`
- `api_update_path`: `wp-json/aimarketing/v1/posts`

## Authentication

```php
function aimarketing_auth(WP_REST_Request $request) {
    $header = $request->get_header('authorization');
    if (! preg_match('/Bearer\s+(.+)/i', $header, $matches)) {
        return new WP_Error('aimarketing_missing_token', 'Missing token', ['status' => 401]);
    }

    $expected = get_option('aimarketing_api_token_hash');
    if (! is_string($expected) || $expected === '') {
        return new WP_Error('aimarketing_not_configured', 'Token is not configured', ['status' => 401]);
    }

    if (! hash_equals($expected, hash('sha256', trim($matches[1])))) {
        return new WP_Error('aimarketing_invalid_token', 'Invalid token', ['status' => 403]);
    }

    return true;
}
```

## Store Post

Use `wp_insert_post`:

- `post_title`: `title`
- `post_content`: `body`
- `post_excerpt`: `description`
- `post_status`: usually `publish`
- `post_category`: resolve from `category_id` or `category_slug`

Return:

```php
return ['url' => get_permalink($post_id)];
```

## Update Post

Find the post from `published_url` with `url_to_postid($published_url)`.

If found, call `wp_update_post`. Return:

```php
return ['success' => true, 'url' => get_permalink($post_id)];
```
