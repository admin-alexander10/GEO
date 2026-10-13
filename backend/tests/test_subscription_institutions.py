import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.subscription_service import SubscriptionService


class TestInstitutionSubscriptions(unittest.TestCase):
    def test_calculate_institution_total_includes_extra_users(self):
        service = SubscriptionService(db=MagicMock())
        service.get_plan_by_code = MagicMock(return_value=SimpleNamespace(
            code="enterprise",
            price=299.0,
            included_users=10,
            extra_seat_price=35.0,
        ))

        total = service.calculate_institution_total("enterprise", 13)

        self.assertEqual(total, 299.0 + (13 - 10) * 35.0)

    def test_add_institution_member_updates_member_count(self):
        service = SubscriptionService(db=MagicMock())
        service.get_plan_by_code = MagicMock(return_value=SimpleNamespace(
            code="enterprise",
            price=299.0,
            included_users=10,
            extra_seat_price=35.0,
        ))

        member = service.add_institution_member(
            institution_name="COER Cajamarca",
            member_name="Ana Torres",
            member_email="ana@coer.pe",
            role="operador",
            total_users=11,
        )

        self.assertEqual(member["institution_name"], "COER Cajamarca")
        self.assertEqual(member["member_name"], "Ana Torres")
        self.assertEqual(member["role"], "operador")
        self.assertEqual(member["monthly_price"], 299.0 + 35.0)
