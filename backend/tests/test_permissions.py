import unittest

from app.core.security import build_permissions_for_role, has_permission


class TestRealPermissions(unittest.TestCase):
    def test_build_permissions_for_role(self):
        permisos = build_permissions_for_role("coordinador")
        self.assertIn("institution:view", permisos)
        self.assertIn("institution:manage", permisos)
        self.assertIn("alert:view", permisos)

    def test_has_permission_uses_role_permissions(self):
        self.assertTrue(has_permission("coordinador", "institution:manage"))
        self.assertFalse(has_permission("ciudadano", "institution:manage"))
