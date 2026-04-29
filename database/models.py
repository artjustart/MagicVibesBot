"""
Модели базы данных для бота Magic Vibes
"""
from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, Integer, Boolean, Float, Text, ForeignKey, Enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import Optional
import enum

class Base(DeclarativeBase):
    pass

class UserRole(enum.Enum):
    CLIENT = "client"
    MANAGER = "manager"
    ADMIN = "admin"

class PracticeType(enum.Enum):
    GROUP = "group"
    INDIVIDUAL = "individual"

class BookingStatus(enum.Enum):
    PENDING = "pending"  # Ожидает оплаты
    CONFIRMED = "confirmed"  # Подтверждена
    CANCELLED = "cancelled"  # Отменена
    COMPLETED = "completed"  # Завершена

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

class CourseType(enum.Enum):
    STARTER = "starter"  # Стартовый онлайн-курс
    THREE_MONTH = "three_month"  # Обучение 3 месяца

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.CLIENT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    course_enrollments: Mapped[list["CourseEnrollment"]] = relationship(back_populates="user")

class Practice(Base):
    __tablename__ = "practices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # довгий опис ("Детальніше")
    practice_type: Mapped[PracticeType] = mapped_column(Enum(PracticeType))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    max_participants: Mapped[Optional[int]] = mapped_column(Integer)  # Только для групповых
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    schedules: Mapped[list["PracticeSchedule"]] = relationship(back_populates="practice")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="practice")

class PracticeSchedule(Base):
    __tablename__ = "practice_schedules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    practice_id: Mapped[int] = mapped_column(ForeignKey("practices.id"))
    datetime: Mapped[datetime] = mapped_column(DateTime)
    available_slots: Mapped[int] = mapped_column(Integer)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    practice: Mapped["Practice"] = relationship(back_populates="schedules")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="schedule")

class Booking(Base):
    __tablename__ = "bookings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    practice_id: Mapped[int] = mapped_column(ForeignKey("practices.id"))
    schedule_id: Mapped[int] = mapped_column(ForeignKey("practice_schedules.id"))
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="bookings")
    practice: Mapped["Practice"] = relationship(back_populates="bookings")
    schedule: Mapped["PracticeSchedule"] = relationship(back_populates="bookings")
    payment: Mapped[Optional["Payment"]] = relationship(back_populates="booking", uselist=False)

class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    booking_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookings.id"))
    course_enrollment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("course_enrollments.id"))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="UAH")
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_provider: Mapped[str] = mapped_column(String(50))  # monopay, etc.
    transaction_id: Mapped[Optional[str]] = mapped_column(String(255))
    payment_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="payments")
    booking: Mapped[Optional["Booking"]] = relationship(back_populates="payment")
    course_enrollment: Mapped[Optional["CourseEnrollment"]] = relationship(back_populates="payment")

class Course(Base):
    __tablename__ = "courses"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    course_type: Mapped[CourseType] = mapped_column(Enum(CourseType))
    price: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(back_populates="course")
    materials: Mapped[list["CourseMaterial"]] = relationship(back_populates="course")

class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    enrolled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Relationships
    user: Mapped["User"] = relationship(back_populates="course_enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")
    payment: Mapped[Optional["Payment"]] = relationship(back_populates="course_enrollment", uselist=False)

class CourseMaterial(Base):
    __tablename__ = "course_materials"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    title: Mapped[str] = mapped_column(String(255))
    file_id: Mapped[str] = mapped_column(String(255))  # Telegram file_id
    file_type: Mapped[str] = mapped_column(String(50))  # document, video, audio
    order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    course: Mapped["Course"] = relationship(back_populates="materials")

class ManagerContact(Base):
    __tablename__ = "manager_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    telegram_username: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    address: Mapped[str] = mapped_column(String(500))
    maps_url: Mapped[str] = mapped_column(String(1000))
    video_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ClosedFormatStatus(enum.Enum):
    NEW = "new"             # тільки створено
    ACCEPTED = "accepted"   # дата погоджена
    PAID = "paid"           # передоплата отримана
    COMPLETED = "completed" # практика проведена
    CANCELLED = "cancelled" # скасовано


class ClosedFormatRequest(Base):
    __tablename__ = "closed_format_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    requested_date_text: Mapped[str] = mapped_column(String(500))
    group_size: Mapped[int] = mapped_column(Integer)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ClosedFormatStatus] = mapped_column(
        Enum(ClosedFormatStatus), default=ClosedFormatStatus.NEW
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Questionnaire(Base):
    """Анкета учасника — JSON у полі data, ключі відповідають ANKETA_QUESTIONS[*]['key']."""
    __tablename__ = "questionnaires"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    data: Mapped[str] = mapped_column(Text)  # JSON-encoded answers
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
