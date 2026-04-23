from sqlalchemy.orm import Session
from database import SessionLocal
import models


def init_db():
    db: Session = SessionLocal()

    # ROLES
    roles = ["admin", "analyst", "user"]
    for role_name in roles:
        exists = db.query(models.Role).filter_by(name=role_name).first()
        if not exists:
            db.add(models.Role(name=role_name))

    # STATUS
    statuses = ["pending", "running", "completed", "failed"]
    for status_name in statuses:
        exists = db.query(models.Status).filter_by(name=status_name).first()
        if not exists:
            db.add(models.Status(name=status_name))

    # TASK TYPES
    task_types = ["scraping", "sentiment_analysis"]
    for task_name in task_types:
        exists = db.query(models.TaskType).filter_by(name=task_name).first()
        if not exists:
            db.add(models.TaskType(name=task_name))

    db.commit()
    db.close()


if __name__ == "__main__":
    init_db()