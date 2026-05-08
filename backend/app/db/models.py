from sqlalchemy import Column, Integer, String, Float, Date, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=True)
    password_hash = Column(String(128), nullable=False)
    name = Column(String(50), nullable=True)
    is_institution = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())


class StockPool(Base):
    """分类股票池：每只股票归属 core(核心) / general(普通) / blacklist(禁买) 之一"""
    __tablename__ = "stock_pool"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(20), nullable=False)
    industry = Column(String(20), default="")
    category = Column(String(16), default="general", index=True)  # core / general / blacklist
    note = Column(String(200), default="")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class StockBasic(Base):
    __tablename__ = "stock_basic"
    id = Column(Integer, primary_key=True, index=True)
    ts_code = Column(String(10), unique=True, index=True, comment="股票代码")
    name = Column(String(20), comment="股票名称")
    industry = Column(String(20), comment="行业")
    list_date = Column(Date, comment="上市日期")

class StockDaily(Base):
    __tablename__ = "stock_daily"
    __table_args__ = (UniqueConstraint("ts_code", "trade_date", name="idx_stock_date"),)
    id = Column(Integer, primary_key=True)
    ts_code = Column(String(10), index=True)
    trade_date = Column(Date, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    vol = Column(Float)
    amount = Column(Float)
    adj_factor = Column(Float, comment="复权因子")

class FactorData(Base):
    __tablename__ = "factor_data"
    __table_args__ = (UniqueConstraint("ts_code", "trade_date", "factor_name"),)
    id = Column(Integer, primary_key=True)
    ts_code = Column(String(10), index=True)
    trade_date = Column(Date, index=True)
    factor_name = Column(String(20))
    factor_value = Column(Float)
    factor_value_neutral = Column(Float)

class BacktestRecord(Base):
    __tablename__ = "backtest_record"
    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(50))
    annual_return = Column(Float)
    max_drawdown = Column(Float)
    sharpe_ratio = Column(Float)
    created_at = Column(DateTime, default=func.now())