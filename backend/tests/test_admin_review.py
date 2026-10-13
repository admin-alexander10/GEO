import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException, Request

from app.api.v1.endpoints.admin import aprobar_solicitud, cambiar_contrasena_propietario, login_propietario, rechazar_solicitud
from app.core.security import decode_access_token
from app.db.base import Base
from app.models.subscription import InstitutionAccount, InstitutionApplication, PlatformAdminAccount
from app.models.user import Usuario
from app.schemas.admin import InstitutionApprovalRequest, InstitutionApplicationItem, InstitutionRejectionRequest, OwnerLoginRequest, OwnerPasswordChangeRequest


class TestInstitutionOwnerReview(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[Usuario.__table__, InstitutionAccount.__table__, InstitutionApplication.__table__, PlatformAdminAccount.__table__],
        )
        self.session = sessionmaker(bind=self.engine)()
        self.session.add_all([
            Usuario(
                usuario="owner-user",
                password="unused",
                rol="director",
                institucion="Policía Regional",
                permisos="[]",
                codigo_enlace="OWNER-1",
                is_active=0,
            ),
            InstitutionAccount(
                institution_name="Policía Regional",
                plan_code="enterprise",
                included_users=10,
                extra_seat_price=35,
                monthly_total=299,
                is_active=False,
            ),
            InstitutionApplication(
                institution_name="Policía Regional",
                ruc="20123456789",
                institution_type="Policía",
                region="Cajamarca",
                official_email="contacto@policia.gob.pe",
                contact_name="Ana Torres",
                contact_phone="976123456",
                evidence_url="https://www.gob.pe/policia",
                applicant_username="owner-user",
                status="pending",
                submitted_at=datetime.utcnow(),
            ),
        ])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_owner_login_issues_scoped_short_lived_token(self):
        request = Request({"type": "http", "client": ("127.0.0.1", 1234)})
        response = login_propietario(OwnerLoginRequest(access_key="admin"), request, self.session)
        claims = decode_access_token(response.access_token)
        self.assertTrue(claims["platform_owner"])
        self.assertTrue(claims["must_change_password"])
        self.assertTrue(response.must_change_password)
        self.assertEqual(response.expires_in, 7200)

        changed = cambiar_contrasena_propietario(
            OwnerPasswordChangeRequest(current_password="admin", new_password="a-new-strong-owner-password"),
            claims,
            self.session,
        )
        self.assertFalse(changed.must_change_password)
        owner_account = self.session.query(PlatformAdminAccount).one()
        self.assertFalse(owner_account.must_change_password)

    def test_default_admin_bootstrap_is_denied_from_remote_host(self):
        request = Request({"type": "http", "client": ("203.0.113.10", 1234)})
        with self.assertRaises(HTTPException) as raised:
            login_propietario(OwnerLoginRequest(access_key="admin"), request, self.session)
        self.assertEqual(raised.exception.status_code, 401)

    def test_approval_audits_source_and_activates_account(self):
        application = self.session.query(InstitutionApplication).one()
        result = aprobar_solicitud(
            application.id,
            InstitutionApprovalRequest(
                verification_source="https://www.gob.pe/policia",
                review_notes="RUC y directorio oficial coinciden.",
            ),
            {"sub": "platform-owner"},
            self.session,
        )
        self.session.refresh(application)
        account = self.session.query(InstitutionAccount).one()
        applicant = self.session.query(Usuario).one()

        self.assertEqual(result.status, "approved")
        self.assertEqual(application.verification_source, "https://www.gob.pe/policia")
        self.assertEqual(application.reviewed_by, "platform-owner")
        self.assertTrue(account.is_active)
        self.assertEqual(applicant.is_active, 1)

    def test_application_response_includes_saved_verification_audit(self):
        application = self.session.query(InstitutionApplication).one()
        item = InstitutionApplicationItem.model_validate(application)
        self.assertEqual(item.ruc, "20123456789")
        self.assertEqual(item.status, "pending")

    def test_approval_rejects_spoofed_government_domain(self):
        application = self.session.query(InstitutionApplication).one()
        with self.assertRaises(HTTPException) as raised:
            aprobar_solicitud(
                application.id,
                InstitutionApprovalRequest(
                    verification_source="https://gob.pe.attacker.example/verify",
                    review_notes="Intento con un dominio que no pertenece al gobierno.",
                ),
                {"sub": "platform-owner"},
                self.session,
            )
        self.assertEqual(raised.exception.status_code, 422)

    def test_rejection_keeps_institution_and_user_disabled(self):
        application = self.session.query(InstitutionApplication).one()
        result = rechazar_solicitud(
            application.id,
            InstitutionRejectionRequest(review_notes="La información no pudo verificarse."),
            {"sub": "platform-owner"},
            self.session,
        )
        self.session.refresh(application)
        account = self.session.query(InstitutionAccount).one()
        applicant = self.session.query(Usuario).one()

        self.assertEqual(result.status, "rejected")
        self.assertFalse(account.is_active)
        self.assertEqual(applicant.is_active, 0)


if __name__ == "__main__":
    unittest.main()
