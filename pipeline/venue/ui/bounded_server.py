"""The lease panel's thread-bounded listener.

The platform serving core's Listener runs an unbounded
ThreadingHTTPServer — one handler thread per request,
spawned as fast as connections arrive. In the panel's
own process (owner ruling: the venue serves
alone because it faces the heaviest usage of the
surfaces) that is the pile-up shape the split exists to
end: parallel state polls against a slow core must queue
at the socket, not multiply threads until the process
drowns.

The bound lives here, in the venue's own serving module,
and nowhere else: the coupled and workbench processes
keep the core's unbounded serving exactly as they were.
The mechanism is a slot taken before a handler thread
spawns and returned when it finishes, so live handler
threads never exceed MAX_HANDLER_THREADS; connections
beyond the bound wait in the listen backlog, and reads
the state cache answers instantly drain the queue as
fast as slots free.
"""

import threading
from http.server import ThreadingHTTPServer

# The ceiling on live request-handler threads in the
# panel's process. The page's parallel part polls fan
# out to seven portions plus its action posts; 32 leaves
# generous headroom over that fan-out while keeping a
# wedged core's thread pile-up at a number the process
# shrugs off.
MAX_HANDLER_THREADS = 32


class BoundedHTTPServer(ThreadingHTTPServer):
    """A ThreadingHTTPServer with a hard ceiling on
    concurrent request-handler threads: process_request
    takes a slot before spawning, and the handler thread
    returns its slot when it finishes — including when
    the spawn itself fails, so a slot never leaks."""

    def __init__(self, server_address, handler_class,
                 max_threads: int = MAX_HANDLER_THREADS):
        self.max_handler_threads = max_threads
        self._handler_slots = threading.BoundedSemaphore(
            max_threads)
        super().__init__(server_address, handler_class)

    def process_request(self, request, client_address):
        self._handler_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._handler_slots.release()
            raise

    def process_request_thread(self, request,
                               client_address):
        try:
            super().process_request_thread(
                request, client_address)
        finally:
            self._handler_slots.release()


def build_bounded_listener(serving, mount, host, port,
                           max_threads: int =
                           MAX_HANDLER_THREADS):
    """A platform serving.Listener whose HTTP server is
    bounded: the Listener the venue process serves on.

    The core's Listener constructs its own unbounded
    ThreadingHTTPServer and offers no server-class seam,
    so the bounded server replaces the listener's httpd —
    same address, same core-generated handler class —
    before serving starts. Everything above the socket
    (routing, reply framing, error containment,
    supervision) is the core's, unchanged; only the
    thread admission is the panel's."""
    listener = serving.Listener(mount, host, port)
    httpd = listener.httpd
    handler_class = httpd.RequestHandlerClass
    address = httpd.server_address
    httpd.server_close()
    listener.httpd = BoundedHTTPServer(
        address, handler_class, max_threads)
    listener.server_address = listener.httpd.server_address
    return listener
