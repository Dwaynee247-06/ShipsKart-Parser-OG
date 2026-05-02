"""
SQLAlchemy ORM models for the product master database.
Tables: Category, Brand, Product
"""
from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Category(Base):
    __tablename__ = "Category"

    CategoryID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    CategoryName: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    Description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")


class Brand(Base):
    __tablename__ = "Brand"

    BrandID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    BrandName: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    Notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="brand")


class Product(Base):
    __tablename__ = "Product"

    ProductID: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ProductName: Mapped[str] = mapped_column(String(200), nullable=False)
    CategoryID: Mapped[int] = mapped_column(Integer, ForeignKey("Category.CategoryID"), nullable=False)
    BrandID: Mapped[int] = mapped_column(Integer, ForeignKey("Brand.BrandID"), nullable=False)
    UnitOfMeasure: Mapped[str] = mapped_column(String(20), nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedAt: Mapped[str | None] = mapped_column(DateTime, server_default=func.now())

    category: Mapped["Category"] = relationship("Category", back_populates="products")
    brand: Mapped["Brand"] = relationship("Brand", back_populates="products")
