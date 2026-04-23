from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    ForeignKey, TIMESTAMP
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from bbdd.database import Base


# =========================
# 👤 USUARIO
# =========================
class User(Base):
    __tablename__ = "usuario"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)

    first_name = Column(String, nullable=False)
    last_name = Column(String)

    roles = relationship("UserRole", back_populates="user")
    analyses = relationship("Analysis", back_populates="user")

    is_active = Column(Boolean, default=True)
    
# =========================
# 🔐 ROLE
# =========================
class Role(Base):
    __tablename__ = "role"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    users = relationship("UserRole", back_populates="role")


# =========================
# 🔗 USER_ROLE (N:M)
# =========================
class UserRole(Base):
    __tablename__ = "user_role"

    user_id = Column(Integer, ForeignKey("usuario.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("role.id"), primary_key=True)

    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users")


# =========================
# 📊 STATUS
# =========================
class Status(Base):
    __tablename__ = "status"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)


# =========================
# 📊 ANALYSIS
# =========================
class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("usuario.id"), nullable=False)

    project_name = Column(String(255), nullable=False, index=True)
    tema = Column(Text)
    output_folder = Column(Text)
    population_scope = Column(Text)

    status_id = Column(Integer, ForeignKey("status.id"))

    created_at = Column(TIMESTAMP, server_default=func.now())

    # relaciones
    user = relationship("User", back_populates="analyses")
    keywords = relationship("Keyword", back_populates="analysis")
    tasks = relationship("AnalysisTask", back_populates="analysis")


# =========================
# 🔑 KEYWORDS
# =========================
class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    analysis_id = Column(Integer, ForeignKey("analysis.id"), nullable=False)

    keyword = Column(Text, nullable=False)
    language = Column(String(50))

    analysis = relationship("Analysis", back_populates="keywords")


# =========================
# ⚙️ TASK TYPE
# =========================
class TaskType(Base):
    __tablename__ = "task_type"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)


# =========================
# ⚙️ ANALYSIS TASK
# =========================
class AnalysisTask(Base):
    __tablename__ = "analysis_task"

    id = Column(Integer, primary_key=True)

    analysis_id = Column(Integer, ForeignKey("analysis.id"), nullable=False)
    task_type_id = Column(Integer, ForeignKey("task_type.id"), nullable=False)
    status_id = Column(Integer, ForeignKey("status.id"), nullable=False)

    progress = Column(Integer, default=0)
    message = Column(Text)

    created_at = Column(TIMESTAMP, server_default=func.now())
    started_at = Column(TIMESTAMP)
    finished_at = Column(TIMESTAMP)

    analysis = relationship("Analysis", back_populates="tasks")