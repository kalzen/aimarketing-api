#!/usr/bin/env python3
"""Kiểm tra một website khách đã tương thích với AI Marketing chưa (hợp đồng API đăng bài).

Mặc định chỉ ĐỌC (ping, xác thực, danh mục, redirect). Thêm --write để đăng một bài thử có nhiều ảnh,
danh mục lạ, URL ảnh rất dài, rồi cập nhật bài đó bằng published_url — bài thử có tiêu đề bắt đầu bằng
"[AIMKT TEST]" và cần xoá tay sau khi chạy.

Chỉ dùng thư viện chuẩn, chạy được trên mọi máy:

    python scripts/smoke_test_api.py --base-url https://khach.vn --token amkt_xxx
    python scripts/smoke_test_api.py --base-url https://khach.vn --token amkt_xxx --write --update-method put
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

TIMEOUT_BUDGET_SECONDS = 30  # AI Marketing chờ tối đa 60s mỗi lượt và thử lại 3 lần: phải nhanh hơn hẳn.

IMAGES = [
    "https://example-cdn.test/1/generated-aaaaaaaa-0000-4000-8000-000000000001.webp",
    "https://example-cdn.test/1/generated-aaaaaaaa-0000-4000-8000-000000000002.jpg",
    "https://example-cdn.test/1/generated-aaaaaaaa-0000-4000-8000-000000000003.png",
]
# URL ký sẵn (signed_fetch) có thể dài cả nghìn ký tự — cột thumbnail varchar(255) sẽ lỗi 500.
LONG_IMAGE = "https://example-cdn.test/1/long.webp?" + "X-Amz-Signature=" + "a" * 1500


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


@dataclass
class Result:
    status: int
    body: str
    headers: dict[str, str]
    seconds: float
    json: object | None = None
    error: str = ""


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, message: str) -> None:
        print(f"  [ OK ] {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"  [FAIL] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"  [WARN] {message}")


def call(method: str, url: str, token: str | None, payload: object | None = None, timeout: int = 60) -> Result:
    headers = {"Accept": "application/json"}
    data = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    started = time.time()
    try:
        with OPENER.open(request, timeout=timeout) as response:
            status, body, response_headers = response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        status, body, response_headers = exc.code, exc.read(), dict(exc.headers)
    except Exception as exc:  # noqa: BLE001
        return Result(0, "", {}, time.time() - started, error=f"{type(exc).__name__}: {exc}")

    text = body.decode("utf-8", errors="replace")
    parsed = None
    try:
        parsed = json.loads(text)
    except ValueError:
        pass

    return Result(status, text, response_headers, time.time() - started, parsed)


def join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def check_read_only(args: argparse.Namespace, report: Report) -> None:
    ping_url = join(args.base_url, args.ping_path)

    print("1. Kết nối, redirect và xác thực")
    plain = call("GET", ping_url, None, timeout=args.timeout)
    if plain.error:
        report.fail(f"Không gọi được {ping_url}: {plain.error}")
        return
    if plain.status in (301, 302, 307, 308):
        location = plain.headers.get("Location", "?")
        report.fail(
            f"{ping_url} bị chuyển hướng ({plain.status}) tới {location}. POST bị đổi thành GET khi đi qua redirect "
            "nên đăng bài sẽ lỗi 405/không có url. Dùng đúng URL cuối cùng (https, www/không www) làm website_url."
        )
        return
    if plain.status in (401, 403):
        report.ok(f"Không có token bị từ chối ({plain.status}).")
    else:
        report.fail(f"Không có token mà trả {plain.status}; phải trả 401/403 trước mọi thao tác ghi.")

    wrong = call("GET", ping_url, "amkt_token_sai_chu_y", timeout=args.timeout)
    if wrong.status in (401, 403):
        report.ok(f"Token sai bị từ chối ({wrong.status}).")
    else:
        report.fail(f"Token sai mà trả {wrong.status}; phải trả 403.")

    good = call("GET", ping_url, args.token, timeout=args.timeout)
    if good.status == 200 and isinstance(good.json, dict) and good.json.get("success") is True:
        report.ok("GET ping với token đúng trả {\"success\": true}.")
    elif good.status in (401, 403):
        report.fail(
            f"Token đúng nhưng bị từ chối ({good.status}). Kiểm tra: raw token vs token hash, config bị cache, "
            "và hosting Apache/FastCGI làm rơi header Authorization (xem references/troubleshooting.md)."
        )
    else:
        report.fail(f"GET ping trả {good.status}: {good.body[:200]!r}")

    print("2. Danh mục (AI chọn danh mục từ danh sách này)")
    categories_url = join(args.base_url, args.categories_path)
    cats = call("GET", categories_url, args.token, timeout=args.timeout)
    if cats.status != 200 or cats.json is None:
        report.warn(
            f"GET {categories_url} trả {cats.status}: bài vẫn đăng được nhưng AI không gợi ý được danh mục."
        )
        return

    items = cats.json.get("categories") if isinstance(cats.json, dict) else cats.json
    if not isinstance(items, list):
        report.fail("Danh mục phải là mảng hoặc {\"categories\": [...]}.")
        return
    named = [c for c in items if isinstance(c, dict) and str(c.get("name") or c.get("title") or c.get("label") or "").strip()]
    if not items:
        report.warn("Website chưa có danh mục nào: AI không có gì để gợi ý (bài vẫn đăng).")
    elif len(named) != len(items):
        report.fail("Có danh mục thiếu name — AI chỉ nhìn thấy name/slug để chọn.")
    else:
        report.ok(f"{len(items)} danh mục hợp lệ (AI sẽ chọn 1 trong số này).")
    if len(items) > 100:
        report.warn("Hơn 100 danh mục: danh sách đưa cho AI quá dài; chỉ trả danh mục dùng được để đăng bài.")
    ids = [str(c.get("id")) for c in named if c.get("id") not in (None, "")]
    if len(ids) != len(set(ids)):
        report.fail("Có danh mục trùng id.")
    junk = [c for c in named if str(c.get("name")).strip().lower() in {"uncategorized", "chưa phân loại", "chua phan loai"}]
    if junk:
        report.warn("Có danh mục 'Uncategorized/Chưa phân loại' — nên bỏ để AI không chọn nhầm.")


def sample_payload(category_id: str | None, category_slug: str | None) -> dict:
    body = (
        "<p>Đoạn mở bài có <strong>chữ đậm</strong> và dấu tiếng Việt đầy đủ: Hải Phòng, tiếng Trung.</p>\n"
        f'<img src="{IMAGES[0]}" alt="Ảnh bìa" />\n'
        "<h2>Phần hai</h2>\nĐoạn chữ trần không có thẻ p, ngăn cách bằng dòng trống.\n\n"
        f'<img src="{IMAGES[1]}" alt="Ảnh giữa bài" />\n'
        "<h3>Phần ba</h3><ul><li>Ý một</li><li>Ý hai</li></ul>\n"
        f'<img src="{IMAGES[2]}" alt="Ảnh cuối bài" />'
    )
    payload = {
        "title": "[AIMKT TEST] " + "Tiêu đề rất dài để thử giới hạn độ dài " * 6,
        "body": body,
        "description": "Mô tả meta " + "x" * 480,
        "faq": [{"question": f"Câu hỏi {i}?", "answer": "Trả lời " * 40} for i in range(1, 4)],
        "image_urls": IMAGES + [LONG_IMAGE],
    }
    if category_id:
        payload["category_id"] = category_id
    if category_slug:
        payload["category_slug"] = category_slug
    return payload


def check_write(args: argparse.Namespace, report: Report) -> None:
    publish_url = join(args.base_url, args.publish_path)
    update_url = join(args.base_url, args.update_path)

    print("3. Đăng bài thử (nhiều ảnh, URL ảnh rất dài, danh mục lạ, trường thừa)")
    payload = sample_payload("__khong_ton_tai__", "khong-ton-tai-slug")
    payload["field_la_khong_co_trong_hop_dong"] = True

    created = call("POST", publish_url, args.token, payload, timeout=args.timeout)
    created_url = ""
    if created.status not in (200, 201):
        report.fail(
            f"POST {publish_url} trả {created.status}: {created.body[:300]!r}. "
            "422 thường do giới hạn title/description/image_urls quá chặt hoặc danh mục lạ bị coi là lỗi; "
            "500 thường do cột thumbnail varchar(255) hoặc lỗi lưu ảnh."
        )
        return
    created_url = str((created.json or {}).get("url", "")) if isinstance(created.json, dict) else ""
    if not created_url.startswith(("http://", "https://")):
        report.fail(f"Đăng xong nhưng không trả url tuyệt đối: {created.body[:200]!r} (AI Marketing coi là lỗi và thử lại → bài trùng).")
        return
    report.ok(f"Đăng được bài thử: {created_url}")
    if created.seconds > TIMEOUT_BUDGET_SECONDS:
        report.warn(f"Đăng mất {created.seconds:.0f}s; AI Marketing timeout 60s và thử lại 3 lần → dễ sinh bài trùng. Nhập ảnh nền/bất đồng bộ.")
    else:
        report.ok(f"Đăng mất {created.seconds:.1f}s (< {TIMEOUT_BUDGET_SECONDS}s).")
    for fragment in ("/public/", "localhost", "127.0.0.1", "/index.php/"):
        if fragment in created_url and fragment not in args.base_url:
            report.fail(f"URL trả về chứa '{fragment}': {created_url}. Phải là URL production gốc.")

    print("4. Trang bài thử hiển thị đủ ảnh")
    page = call("GET", created_url, None, timeout=args.timeout)
    if page.status != 200:
        report.fail(f"Mở {created_url} trả {page.status}.")
    else:
        found = [image for image in IMAGES if image.split("/")[-1] in page.body]
        if len(found) == len(IMAGES):
            report.ok("Trang có đủ 3/3 ảnh trong nội dung (hoặc ảnh đã nhập về dưới tên khác — xác nhận bằng mắt).")
        elif page.body and "<img" not in page.body.lower():
            report.fail("Trang không có thẻ <img> nào: ảnh trong body bị lọc mất.")
        else:
            report.warn(f"Chỉ thấy {len(found)}/3 tên ảnh gốc trong HTML (đúng nếu site tải ảnh về và đổi URL).")
        if "{{IMAGE_URL" in page.body:
            report.fail("Trang còn placeholder {{IMAGE_URL_N}}.")

    print("5. Gửi lại y hệt (mô phỏng AI Marketing thử lại khi timeout)")
    again = call("POST", publish_url, args.token, payload, timeout=args.timeout)
    again_url = str((again.json or {}).get("url", "")) if isinstance(again.json, dict) else ""
    if again_url and again_url == created_url:
        report.ok("Gửi lại cùng nội dung trả về cùng một url (không tạo bài trùng).")
    elif again_url:
        report.warn(
            f"Gửi lại cùng nội dung tạo bài mới ({again_url}). Nên chặn trùng (cùng title+body trong 15 phút) "
            "để lượt thử lại của AI Marketing không sinh bài thừa. Nhớ xoá cả bài này."
        )

    print("6. Cập nhật bài bằng published_url (phải sửa ĐÚNG bài đó, không tạo bài mới)")
    update_payload = sample_payload(None, None)
    update_payload.update(
        {
            "published_url": created_url,
            "title": "[AIMKT TEST] đã sửa",
            "force_replace_images": True,
            "replace_images": True,
        }
    )
    method = "PUT" if args.update_method == "put" else "POST"
    updated = call(method, update_url, args.token, update_payload, timeout=args.timeout)
    if updated.status not in (200, 201):
        report.fail(f"{method} {update_url} trả {updated.status}: {updated.body[:300]!r}")
        return
    result = updated.json if isinstance(updated.json, dict) else {}
    new_url = str(result.get("url", ""))
    if result.get("success") is not True and not new_url:
        report.fail("Cập nhật phải trả {\"success\": true} hoặc {\"url\": ...}.")
    elif new_url and new_url.rstrip("/") != created_url.rstrip("/"):
        report.fail(
            f"Cập nhật trả url khác ({new_url} ≠ {created_url}) — website đã TẠO BÀI MỚI thay vì sửa bài cũ. "
            "Nếu chỉ PUT mới sửa được: đặt api_update_method=put trong cài đặt dự án AI Marketing, "
            "và/hoặc cho POST có published_url hoạt động như cập nhật."
        )
    else:
        report.ok("Cập nhật giữ nguyên url của bài.")

    recheck = call("GET", created_url, None, timeout=args.timeout)
    if recheck.status == 200 and "đã sửa" in recheck.body:
        report.ok("Tiêu đề mới hiện trên trang.")
    elif recheck.status == 200:
        report.warn("Trang chưa hiện tiêu đề mới (cache trang?). Kiểm tra lại sau vài phút.")

    print("\nBài thử cần xoá tay trên website:")
    print(f"  - {created_url}")
    if again_url and again_url != created_url:
        print(f"  - {again_url}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test hợp đồng API đăng bài AI Marketing.")
    parser.add_argument("--base-url", required=True, help="website_url đang cấu hình trong AI Marketing")
    parser.add_argument("--token", required=True, help="API token (dạng thô) cấu hình trong AI Marketing")
    parser.add_argument("--ping-path", default="api/ping")
    parser.add_argument("--categories-path", default="api/posts/categories")
    parser.add_argument("--publish-path", default="api/posts")
    parser.add_argument("--update-path", default="api/posts")
    parser.add_argument("--update-method", choices=("post", "put"), default="post", help="project.settings.api_update_method")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--write", action="store_true", help="Đăng + cập nhật một bài thử (cần xoá tay sau đó)")
    args = parser.parse_args()

    parsed = urllib.parse.urlparse(args.base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        print("--base-url phải là URL đầy đủ, ví dụ https://khach.vn", file=sys.stderr)
        return 2

    report = Report()
    check_read_only(args, report)
    if args.write and not report.failures:
        check_write(args, report)
    elif args.write:
        print("\nBỏ qua phần ghi vì phần đọc đã lỗi — sửa xong chạy lại.")

    print(f"\nKết quả: {len(report.failures)} lỗi, {len(report.warnings)} cảnh báo.")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
