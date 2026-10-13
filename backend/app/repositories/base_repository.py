from typing import TypeVar, Generic, Type, Optional, List, Any
from sqlalchemy.orm import Session
from app.domain.interfaces.repositories import IBaseRepository

T = TypeVar("T")

class BaseRepository(IBaseRepository[T], Generic[T]):
    """Implementación base genérica de repositorio con SQLAlchemy."""

    def __init__(self, db: Session, model_cls: Type[T]):
        self.db = db
        self.model_cls = model_cls

    def get_by_id(self, id: Any) -> Optional[T]:
        return self.db.query(self.model_cls).filter(self.model_cls.id == id).first()

    def list_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        return self.db.query(self.model_cls).offset(skip).limit(limit).all()

    def create(self, entity: T) -> T:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, id: Any) -> bool:
        record = self.get_by_id(id)
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False
