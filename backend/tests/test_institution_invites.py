import hashlib
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import decode_access_token, hash_password
from app.db.base import Base
from app.models.subscription import InstitutionAccount, InstitutionApplication, InstitutionInvite, InstitutionMember, PlanCatalog
from app.models.user import Usuario
from app.schemas.auth import LoginRequest, RegistroRequest
from app.services.auth_service import AuthService


class TestInstitutionInvites(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[
                Usuario.__table__,
                InstitutionInvite.__table__,
                InstitutionMember.__table__,
                InstitutionAccount.__table__,
                InstitutionApplication.__table__,
                PlanCatalog.__table__,
            ],
        )
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_public_registration_cannot_assign_privileged_role(self):
        response = AuthService(self.session).registrar_usuario(RegistroRequest(
            usuario="public-user",
            password="long-password",
            rol="director",
            institucion="Other institution",
        ))

        self.assertEqual(response.rol, "ciudadano")
        self.assertEqual(response.institucion, "individual")
        self.assertNotIn("institution:manage", response.permisos)

    def test_public_institution_registration_waits_for_approval(self):
        service = AuthService(self.session)
        response = service.registrar_usuario(RegistroRequest(
            usuario="coer-director",
            password="a-strong-password",
            modo="institucional",
            nombre_institucion="COER Cajamarca",
            ruc_institucion="20123456789",
            tipo_institucion="COER",
            region_institucion="Cajamarca",
            correo_institucional="contacto@coer.gob.pe",
            contacto_institucional="Ana Torres",
            telefono_institucional="976123456",
            evidencia_institucional_url="https://www.gob.pe/",
        ))

        owner = self.session.query(Usuario).filter(Usuario.usuario == "coer-director").one()
        institution = self.session.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == "COER Cajamarca"
        ).one()
        self.assertEqual(response.rol, "director")
        self.assertIsNone(response.token)
        self.assertEqual(owner.is_active, 0)
        self.assertFalse(institution.is_active)
        with self.assertRaises(Exception):
            service.autenticar_usuario(LoginRequest(
                usuario="coer-director",
                password="a-strong-password",
                modo="institucional",
            ))

    def test_existing_citizen_can_request_institutional_conversion(self):
        self.session.add(Usuario(
            usuario="mcajamarca",
            password=hash_password("existing-account-password"),
            rol="ciudadano",
            institucion="individual",
            codigo_enlace="CITIZEN-MCAJAMARCA",
            is_active=1,
        ))
        self.session.commit()

        response = AuthService(self.session).registrar_usuario(RegistroRequest(
            usuario="mcajamarca",
            password="existing-account-password",
            modo="institucional",
            nombre_institucion="POLICIA",
            ruc_institucion="20123456780",
            tipo_institucion="Policía",
            region_institucion="Cajamarca",
            correo_institucional="contacto@policia.gob.pe",
            contacto_institucional="Ana Torres",
            telefono_institucional="976123456",
            evidencia_institucional_url="https://www.gob.pe/",
        ))
        account = self.session.query(Usuario).filter(Usuario.usuario == "mcajamarca").one()
        institution = self.session.query(InstitutionAccount).filter(
            InstitutionAccount.institution_name == "POLICIA"
        ).one()
        application = self.session.query(InstitutionApplication).filter(
            InstitutionApplication.applicant_username == "mcajamarca"
        ).one()

        # La solicitud queda pendiente y la institución desactivada...
        self.assertIsNone(response.token)
        self.assertEqual(application.status, "pending")
        self.assertFalse(institution.is_active)
        # ...pero el ciudadano NO pierde su cuenta mientras espera la revisión.
        self.assertEqual(response.rol, "ciudadano")
        self.assertEqual(account.rol, "ciudadano")
        self.assertEqual(account.institucion, "individual")
        self.assertEqual(account.is_active, 1)
        login = AuthService(self.session).autenticar_usuario(LoginRequest(
            usuario="mcajamarca", password="existing-account-password", modo="familiar"
        ))
        self.assertEqual(login.rol, "ciudadano")

    def test_invitation_creates_account_and_is_single_use(self):
        raw_token = "invitation-token-for-one-time-acceptance"
        invite = InstitutionInvite(
            institution_name="COER Cajamarca",
            member_name="Ana Torres",
            email="ana@example.org",
            role="operador",
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        self.session.add(invite)
        self.session.commit()

        response = AuthService(self.session).aceptar_invitacion(raw_token, "a-strong-password-123")
        token_payload = decode_access_token(response.token)
        member = self.session.query(InstitutionMember).one()
        account = self.session.query(Usuario).one()

        self.assertEqual(response.rol, "operador")
        self.assertEqual(response.institucion, "COER Cajamarca")
        self.assertEqual(token_payload["sub"], "ana@example.org")
        self.assertEqual(member.email, account.usuario)
        with self.assertRaises(Exception):
            AuthService(self.session).aceptar_invitacion(raw_token, "a-strong-password-123")

    def test_login_mode_must_match_account_type(self):
        self.session.add_all([
            Usuario(
                usuario="citizen",
                password=hash_password("citizen-password"),
                rol="ciudadano",
                institucion="individual",
                codigo_enlace="CITIZEN-1",
            ),
            Usuario(
                usuario="operator@example.org",
                password=hash_password("institution-password"),
                rol="operador",
                institucion="COER Cajamarca",
                codigo_enlace="OPERATOR-1",
            ),
        ])
        self.session.commit()
        service = AuthService(self.session)

        citizen = service.autenticar_usuario(LoginRequest(
            usuario="citizen", password="citizen-password", modo="familiar"
        ))
        operator = service.autenticar_usuario(LoginRequest(
            usuario="operator@example.org", password="institution-password", modo="institucional"
        ))

        self.assertEqual(citizen.rol, "ciudadano")
        self.assertEqual(operator.institucion, "COER Cajamarca")
        with self.assertRaises(Exception):
            service.autenticar_usuario(LoginRequest(
                usuario="citizen", password="citizen-password", modo="institucional"
            ))
        with self.assertRaises(Exception):
            service.autenticar_usuario(LoginRequest(
                usuario="operator@example.org", password="institution-password", modo="familiar"
            ))


if __name__ == "__main__":
    unittest.main()
