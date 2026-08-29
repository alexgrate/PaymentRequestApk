"""Keep this application out of search engines.

The meta tag in base.html covers HTML pages, but not the CSV and Excel
downloads - a header is the only way to mark those, so it is applied to every
response here rather than per template.

Note this is a request that well-behaved crawlers honour, not access control.
The app already requires a login, so there is no payment data for a crawler to
reach; this stops the sign-in page itself being indexed and listed.
"""

ROBOTS_DIRECTIVE = "noindex, nofollow, noarchive, nosnippet, noimageindex, notranslate"


class NoIndexMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Robots-Tag"] = ROBOTS_DIRECTIVE
        return response
