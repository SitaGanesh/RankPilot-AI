from unittest.mock import patch

from django.test import TestCase

from audits.models import Audit, CrawlLink, CrawlURL
from collector.fetcher import FetchedPage
from collector.technical_resources import ResourceObservation
from core.errors import FetchError, HTTPStatusError, NonHTMLResponseError, SecurityError
from discovery.service import CrawlLimits, URLDiscoveryService, normalize_url


def page(url, html, status=200):
    return FetchedPage(
        requested_url=url,
        normalized_url=url,
        final_url=url,
        redirect_chain=[],
        status=status,
        headers={"content-type": "text/html"},
        body=html.encode(),
        fetch_timing_ms=1,
    )


class DiscoveryTests(TestCase):
    def setUp(self):
        self.audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
        )
        self.resolve = patch(
            "core.security.resolve_public_host", return_value=["93.184.216.34"]
        )
        self.resolve.start()
        self.addCleanup(self.resolve.stop)

    def resource(self, url, allowed_content_types, request_hook=None):
        if url.endswith("robots.txt"):
            return ResourceObservation(
                requested_url=url,
                final_url=url,
                status=200,
                content_type="text/plain",
                body=b"Sitemap: https://example.com/sitemap.xml",
            )
        if url.endswith("sitemap.xml"):
            return ResourceObservation(
                requested_url=url,
                final_url=url,
                status=200,
                content_type="application/xml",
                body=b"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                b"<url><loc>https://example.com/from-sitemap</loc></url></urlset>",
            )
        return ResourceObservation(requested_url=url, error="not found")

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_bfs_persists_homepage_nested_links_and_sitemap(self, fetch_page, fetch_resource):
        fetch_resource.side_effect = self.resource
        fetch_page.side_effect = lambda url, request_hook=None: page(
            url,
            {
                "https://example.com/": '<a href="/one#section">one</a><a href="https://outside.test/x">outside</a>',
                "https://example.com/one": '<a href="/two/">two</a><a href="/one/">cycle</a>',
                "https://example.com/two": "<p>done</p>",
                "https://example.com/from-sitemap": "<p>sitemap</p>",
            }[url],
        )

        found = URLDiscoveryService(
            self.audit, CrawlLimits(max_pages=10, max_depth=3, per_host_requests=20)
        ).run()

        self.assertEqual(
            {item.url for item in found},
            {
                "https://example.com/",
                "https://example.com/one",
                "https://example.com/two",
                "https://example.com/from-sitemap",
            },
        )
        self.assertEqual(CrawlURL.objects.filter(status=CrawlURL.Status.FETCHED).count(), 4)
        self.assertEqual(CrawlLink.objects.count(), 3)
        self.assertFalse(CrawlURL.objects.filter(url__contains="outside").exists())
        self.assertEqual(
            CrawlURL.objects.get(url="https://example.com/from-sitemap").discovery_source,
            CrawlURL.DiscoverySource.SITEMAP,
        )
        self.assertEqual(
            CrawlURL.objects.get(url="https://example.com/one").discovery_source,
            CrawlURL.DiscoverySource.INTERNAL_LINK,
        )

    @patch("discovery.service.fetch_resource", side_effect=FetchError("bad sitemap"))
    @patch("discovery.service.fetch_page")
    def test_failed_page_and_malformed_sitemap_are_recorded_without_aborting(
        self, fetch_page, fetch_resource
    ):
        fetch_page.side_effect = [
            page("https://example.com/", '<a href="/missing">missing</a>'),
            FetchError("timeout"),
        ]

        URLDiscoveryService(self.audit, CrawlLimits(max_pages=5)).run()

        self.assertEqual(CrawlURL.objects.filter(status=CrawlURL.Status.FAILED).count(), 1)
        self.assertEqual(CrawlURL.objects.get(url="https://example.com/missing").error, "timeout")

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_page_and_depth_limits_skip_pending_urls(self, fetch_page, fetch_resource):
        fetch_resource.side_effect = self.resource
        def fetch(url, request_hook=None):
            request_hook()
            return page(url, '<a href="/one"><a href="/two"><a href="/three">')

        fetch_page.side_effect = fetch

        URLDiscoveryService(
            self.audit, CrawlLimits(max_pages=5, max_depth=1, per_host_requests=3)
        ).run()

        self.assertLessEqual(CrawlURL.objects.count(), 5)
        self.assertEqual(
            set(CrawlURL.objects.values_list("status", flat=True)),
            {CrawlURL.Status.FETCHED, CrawlURL.Status.SKIPPED},
        )
        self.assertTrue(all(depth <= 1 for depth in CrawlURL.objects.values_list("depth", flat=True)))

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_conventional_sitemap_fallback_when_robots_has_no_declaration(
        self, fetch_page, fetch_resource
    ):
        def resource(url, allowed_content_types, request_hook=None):
            if request_hook is not None:
                request_hook()
            if url.endswith("sitemap.xml"):
                return ResourceObservation(
                    requested_url=url,
                    final_url=url,
                    status=200,
                    content_type="application/xml",
                    body=b"<urlset><url><loc>/fallback</loc></url></urlset>",
                )
            return ResourceObservation(
                requested_url=url, final_url=url, status=200, content_type="text/plain"
            )

        fetch_resource.side_effect = resource
        fetch_page.side_effect = lambda url, request_hook=None: page(url, "<p>page</p>")

        URLDiscoveryService(
            self.audit, CrawlLimits(max_pages=5, per_host_requests=10)
        ).run()

        self.assertTrue(CrawlURL.objects.filter(url="https://example.com/fallback").exists())

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_malformed_sitemap_xml_is_ignored(self, fetch_page, fetch_resource):
        fetch_resource.side_effect = lambda url, allowed, request_hook=None: (
            ResourceObservation(
                requested_url=url,
                final_url=url,
                status=200,
                content_type="application/xml",
                body=b"<urlset>",
            )
            if "sitemap" in url
            else ResourceObservation(requested_url=url, error="missing")
        )
        fetch_page.side_effect = lambda url, request_hook=None: page(url, "<p>page</p>")

        URLDiscoveryService(self.audit, CrawlLimits(per_host_requests=10)).run()

        self.assertEqual(
            set(CrawlURL.objects.values_list("url", flat=True)),
            {"https://example.com/"},
        )

    def test_sitemap_page_locations_exclude_image_metadata(self):
        from discovery.service import _sitemap_locations

        locations, is_index = _sitemap_locations(
            b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'
                xmlns:image='http://www.google.com/schemas/sitemap-image/1.1'>
                <url><loc>/page</loc><image:image><image:loc>/hero.jpg</image:loc>
                </image:image></url></urlset>"""
        )

        self.assertFalse(is_index)
        self.assertEqual(locations, ["/page"])

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_sitemap_media_loc_is_skipped_as_media_not_failed_page(
        self, fetch_page, fetch_resource
    ):
        def resource(url, allowed, request_hook=None):
            if request_hook:
                request_hook()
            if url.endswith("robots.txt"):
                return ResourceObservation(
                    requested_url=url,
                    final_url=url,
                    status=200,
                    content_type="text/plain",
                    body=b"Sitemap: https://example.com/sitemap.xml",
                )
            if url.endswith("sitemap.xml"):
                return ResourceObservation(
                    requested_url=url,
                    final_url=url,
                    status=200,
                    content_type="application/xml",
                    body=b"<urlset><url><loc>/page</loc></url><url><loc>/hero.jpg</loc></url></urlset>",
                )
            return ResourceObservation(requested_url=url, error="missing")

        def fetch(url, request_hook=None):
            if request_hook:
                request_hook()
            if url.endswith(".jpg"):
                raise NonHTMLResponseError(
                    "Response Content-Type is not HTML", 200, url, "image/jpeg"
                )
            return page(url, "<p>page</p>")

        fetch_resource.side_effect = resource
        fetch_page.side_effect = fetch

        URLDiscoveryService(self.audit, CrawlLimits(per_host_requests=20)).run()

        media = CrawlURL.objects.get(url="https://example.com/hero.jpg")
        self.assertEqual(media.resource_type, CrawlURL.ResourceType.MEDIA)
        self.assertEqual(media.status, CrawlURL.Status.SKIPPED)
        self.assertEqual(media.response_status, 200)
        self.assertIn("image/jpeg", media.error)
        self.assertEqual(CrawlURL.objects.get(url="https://example.com/page").status, CrawlURL.Status.FETCHED)

    @patch("discovery.service.fetch_resource", side_effect=FetchError("missing sitemap"))
    @patch("discovery.service.fetch_page")
    def test_content_type_classification_allows_extensionless_and_image_suffix_html(
        self, fetch_page, fetch_resource
    ):
        def fetch(url, request_hook=None):
            if request_hook:
                request_hook()
            html = (
                '<a href="/extensionless">html</a><a href="/looks-like-image.jpg">html</a>'
                if url == "https://example.com/"
                else "<p>html</p>"
            )
            return page(url, html)

        fetch_page.side_effect = fetch

        URLDiscoveryService(self.audit, CrawlLimits(max_depth=1, per_host_requests=20)).run()

        for url in ("https://example.com/extensionless", "https://example.com/looks-like-image.jpg"):
            item = CrawlURL.objects.get(url=url)
            self.assertEqual(item.status, CrawlURL.Status.FETCHED)
            self.assertEqual(item.resource_type, CrawlURL.ResourceType.PAGE)

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_request_budget_includes_robots_sitemaps_and_pages(
        self, fetch_page, fetch_resource
    ):
        calls = []

        def resource(url, allowed, request_hook=None):
            request_hook()
            calls.append(url)
            return ResourceObservation(
                requested_url=url, final_url=url, status=200, content_type="text/plain"
            )

        def fetch(url, request_hook=None):
            request_hook()
            calls.append(url)
            return page(url, "<p>page</p>")

        fetch_resource.side_effect = resource
        fetch_page.side_effect = fetch

        URLDiscoveryService(self.audit, CrawlLimits(per_host_requests=2)).run()

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls, ["https://example.com/robots.txt", "https://example.com/sitemap.xml"])

    def test_normalization_removes_fragment_and_collapses_trailing_slash(self):
        self.assertEqual(
            normalize_url("HTTPS://EXAMPLE.COM/path///?q=1#part"),
            "https://example.com/path?q=1",
        )

    @patch("discovery.service.fetch_resource")
    @patch("discovery.service.fetch_page")
    def test_sitemap_index_discovers_child_sitemap_without_filename_heuristics(
        self, fetch_page, fetch_resource
    ):
        def resource(url, allowed_content_types, request_hook=None):
            if url.endswith("robots.txt"):
                return ResourceObservation(
                    requested_url=url,
                    final_url=url,
                    status=200,
                    content_type="text/plain",
                    body=b"Sitemap: https://example.com/index",
                )
            if url.endswith("/index"):
                body = (
                    b"<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                    b"<sitemap><loc>/child-map</loc></sitemap></sitemapindex>"
                )
            else:
                body = (
                    b"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                    b"<url><loc>/nested</loc></url></urlset>"
                )
            return ResourceObservation(
                requested_url=url,
                final_url=url,
                status=200,
                content_type="application/xml",
                body=body,
            )

        fetch_resource.side_effect = resource
        fetch_page.side_effect = lambda url, request_hook=None: page(url, "<p>page</p>")

        URLDiscoveryService(self.audit, CrawlLimits(max_pages=5)).run()

        self.assertTrue(CrawlURL.objects.filter(url="https://example.com/nested").exists())

    @patch("discovery.service.fetch_page", side_effect=SecurityError("unsafe redirect"))
    @patch("discovery.service.fetch_resource", side_effect=FetchError("unavailable"))
    def test_security_failure_is_a_failed_frontier_item(self, fetch_resource, fetch_page):
        URLDiscoveryService(self.audit).run()
        item = CrawlURL.objects.get()
        self.assertEqual(item.status, CrawlURL.Status.FAILED)
        self.assertEqual(item.error, "unsafe redirect")

    @patch("discovery.service.fetch_resource", side_effect=FetchError("unavailable"))
    @patch("discovery.service.fetch_page")
    def test_http_error_is_failed_but_status_and_final_url_are_retained(
        self, fetch_page, fetch_resource
    ):
        fetch_page.return_value = page(
            "https://example.com/",
            "<p>not found</p>",
            status=404,
        )

        URLDiscoveryService(self.audit, CrawlLimits(per_host_requests=10)).run()

        item = CrawlURL.objects.get()
        self.assertEqual(item.status, CrawlURL.Status.FAILED)
        self.assertEqual(item.response_status, 404)
        self.assertEqual(item.final_url, "https://example.com/")
        self.assertEqual(item.error, "HTTP response status 404")

    @patch("discovery.service.fetch_resource", side_effect=FetchError("unavailable"))
    @patch(
        "discovery.service.fetch_page",
        side_effect=HTTPStatusError("unsupported redirect status", 304),
    )
    def test_unsupported_final_redirect_is_failed_with_status(
        self, fetch_page, fetch_resource
    ):
        URLDiscoveryService(self.audit, CrawlLimits(per_host_requests=10)).run()

        item = CrawlURL.objects.get()
        self.assertEqual(item.status, CrawlURL.Status.FAILED)
        self.assertEqual(item.response_status, 304)
