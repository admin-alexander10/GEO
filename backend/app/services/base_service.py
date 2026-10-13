from sqlalchemy.orm import Session

class BaseService:
    """Clase base para todos los servicios de la capa de aplicación."""
    def __init__(self, db: Session):
        self.db = db
