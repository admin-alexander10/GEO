import unittest

from app.services.realtime import InstitutionalAlertHub


class FakeWebSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


class TestInstitutionalRealtime(unittest.IsolatedAsyncioTestCase):
    async def test_alert_events_are_tenant_scoped(self):
        hub = InstitutionalAlertHub()
        coer_socket = FakeWebSocket()
        other_socket = FakeWebSocket()
        hub.connect("COER Cajamarca", coer_socket)
        hub.connect("Bomberos Cajamarca", other_socket)

        await hub.publish_alert("COER Cajamarca", {"type": "alert.created"})

        self.assertEqual(coer_socket.events, [{"type": "alert.created"}])
        self.assertEqual(other_socket.events, [])


if __name__ == "__main__":
    unittest.main()
