"""
SEO and Search Engine Indexing Views for GRANDEC LMS.
Serves dynamic /sitemap.xml and /robots.txt.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from django.http import HttpRequest, HttpResponse
from django.utils import timezone


def sitemap_xml_view(request: HttpRequest) -> HttpResponse:
    """
    Generate dynamic XML sitemap containing static pages and published tests/courses.
    """
    site_url = "https://grandec.uz"
    today_str = timezone.now().strftime("%Y-%m-%d")

    # Static core routes: (loc, lastmod, changefreq, priority)
    urls = [
        (f"{site_url}/", today_str, "daily", "1.0"),
        (f"{site_url}/pricing", today_str, "weekly", "0.8"),
    ]

    # Learning content requires authentication and has no public detail route.
    # A published test/course is not, by itself, a publicly indexable page.
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for loc, lastmod, changefreq, priority in urls:
        xml_parts.append(
            f"  <url>\n"
            f"    <loc>{escape(loc)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    xml_parts.append("</urlset>")
    content = "\n".join(xml_parts)

    return HttpResponse(content, content_type="application/xml; charset=utf-8")


def robots_txt_view(request: HttpRequest) -> HttpResponse:
    """
    Generate standard robots.txt directing search bots to sitemap and protecting internal APIs.
    """
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /control-panel/\n"
        "Disallow: /tma/\n\n"
        "Sitemap: https://grandec.uz/sitemap.xml\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")
