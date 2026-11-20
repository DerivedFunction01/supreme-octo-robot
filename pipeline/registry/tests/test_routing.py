"""Routing tables (contract 01): each table resolves by
its own rule — wake owners never guess, notify falls back
to main, restart resolves exact → namespace → prefix and
reports the rest unresolved."""

import unittest

from registry.callers import routing
from registry.store import Registry


def make_registry():
    return Registry({
        "routing": {
            "bridge_wake_owners": {
                "version": 1,
                "owners": {"token-caller": {"chat": "chat-owner"}},
                "drain": {"chat": "chat-drain"},
            },
            "notify_routes": {
                "main": "chat-main",
                "routes": {"thread-a": "chat-a"},
            },
            "restart_owners": {
                "owners": {"exact-caller": {"chat": "chat-exact"}},
                "namespaces": {"ns-caller": {"chat": "chat-ns"}},
                "prefixes": {"pre-": {"chat": "chat-pre"}},
            },
        },
    })


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry()

    def test_wake_owner_and_drain(self):
        self.assertEqual(
            routing.wake_owner(self.registry, "token-caller"),
            "chat-owner")
        self.assertIsNone(routing.wake_owner(self.registry, "other"))
        self.assertEqual(routing.wake_drain(self.registry), "chat-drain")

    def test_notify_route_and_main_fallback(self):
        self.assertEqual(
            routing.notify_route(self.registry, "thread-a"), "chat-a")
        self.assertEqual(
            routing.notify_route(self.registry, "panel"), "chat-main")
        self.assertEqual(
            routing.notify_route(self.registry, "unknown"), "chat-main")

    def test_restart_grammar(self):
        self.assertEqual(
            routing.restart_owner(self.registry, "exact-caller"),
            "chat-exact")
        self.assertEqual(
            routing.restart_owner(self.registry, "ns-caller:lane-2"),
            "chat-ns")
        self.assertEqual(
            routing.restart_owner(self.registry, "pre-fixed"),
            "chat-pre")
        self.assertIsNone(
            routing.restart_owner(self.registry, "nobody"))

    def test_empty_registry_resolves_nothing(self):
        empty = Registry.empty()
        self.assertIsNone(routing.wake_owner(empty, "token-caller"))
        self.assertIsNone(routing.notify_route(empty, "panel"))
        self.assertIsNone(routing.restart_owner(empty, "exact-caller"))


if __name__ == "__main__":
    unittest.main()
