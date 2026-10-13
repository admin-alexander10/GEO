import unittest

from main import app


class TestAppRoutes(unittest.TestCase):
    def test_versioned_routes_are_exposed_once_in_openapi(self):
        paths = set(app.openapi().get("paths", {}).keys())

        self.assertIn("/api/v1/auth/registro/", paths)
        self.assertIn("/api/v1/auth/login/", paths)
        self.assertIn("/api/v1/alertas/despachar/", paths)
        self.assertIn("/api/v1/security/anti-theft-alert", paths)
        self.assertIn("/api/v1/subscriptions/plans", paths)
        self.assertIn("/api/v1/subscriptions/checkout", paths)
        self.assertIn("/api/v1/admin/login", paths)
        self.assertIn("/api/v1/admin/institution-applications", paths)
        self.assertIn("/api/v1/admin/institution-applications/{application_id}/approve", paths)
        self.assertIn("/api/v1/admin/institution-applications/{application_id}/reject", paths)

        self.assertNotIn("/auth/registro/", paths)
        self.assertNotIn("/auth/login/", paths)
        self.assertNotIn("/alertas/despachar/", paths)
        self.assertNotIn("/security/anti-theft-alert", paths)
        self.assertNotIn("/subscriptions/plans", paths)
        self.assertNotIn("/subscriptions/checkout", paths)
        self.assertFalse(any("/institutions/requests/" in path for path in paths))
        self.assertFalse(any(path.endswith("/institutions/provision") for path in paths))


if __name__ == "__main__":
    unittest.main()
