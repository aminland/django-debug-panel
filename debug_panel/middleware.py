"""
Debug Panel middleware
"""
import threading
import time
import types

from django.conf import settings
from django.core.urlresolvers import reverse, resolve, Resolver404

from debug_toolbar.middleware import DebugToolbarMiddleware

from debug_panel.cache import cache

# the urls patterns that concern only the debug_panel application
import debug_panel.urls


def show_toolbar(request):
    if request.META.get('REMOTE_ADDR', None) not in settings.INTERNAL_IPS:
        return False

    try:
        match = resolve(request.path)
    except Resolver404:
        pass
    else:
        if match.func.__module__.startswith('debug_toolbar.'):
            return False

    return bool(settings.DEBUG)


class DebugPanelMiddleware(DebugToolbarMiddleware):
    """
    Middleware to set up Debug Panel on incoming request and render toolbar
    on outgoing response.
    """


    def process_request(self, request):
        """
        Try to match the request with a URL from the debug_panel application.

        If it matches, that means we are serving a view from debug_panel,
        and we can skip the debug_toolbar middleware.

        Otherwise we fallback to the default debug_toolbar middleware.
        """

        try:
            res = resolve(request.path, urlconf=debug_panel.urls)
        except Resolver404:
            return super(DebugPanelMiddleware, self).process_request(request)

        return res.func(request, *res.args, **res.kwargs)


    def process_response(self, request, response):
        """
        In addition to rendering the toolbar inside the response HTML, store it
        in the Django cache.

        The data stored in the cache is then reachable from a URL that is
        appened to the HTTP response header under the 'X-debug-data-url' key.
        """
        toolbar = self.__class__.debug_toolbars.get(threading.current_thread().ident)

        if toolbar:
            toolbar._rendered_output = None

            original_render_toolbar = toolbar.render_toolbar
            def cache_rendered_output(toolbar):
                if toolbar._rendered_output is None:
                    toolbar._rendered_output = original_render_toolbar()
                return toolbar._rendered_output
            toolbar.render_toolbar = types.MethodType(cache_rendered_output, toolbar)

        response = super(DebugPanelMiddleware, self).process_response(request, response)

        if toolbar:
            timestamp = str(time.time())
            cache_key = "django-debug-panel:" + timestamp
            cache.set(cache_key, toolbar.render_toolbar())

            response['X-debug-data-url'] = request.build_absolute_uri(
                reverse('debug_data', urlconf=debug_panel.urls, kwargs={'timestamp': timestamp}))

        return response
