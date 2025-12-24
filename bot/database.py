from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import sqlite3

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True)
    username = Column(String)
    full_name = Column(String)
    role = Column(String, default='user')  # admin, agent, user
    created_at = Column(DateTime, default=datetime.now)
    
    # Данные агента
    card_number = Column(String, nullable=True)
    account_number = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Отношения
    transactions = relationship("Transaction", back_populates="agent")
    session_data = relationship("Session", back_populates="agent")

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('users.id'))
    phone_number = Column(String)
    amount = Column(Integer)
    bank = Column(String)
    email = Column(String)
    timestamp = Column(DateTime, default=datetime.now)
    
    agent = relationship("User", back_populates="transactions")

class Session(Base):
    __tablename__ = 'sessions'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('users.id'))
    target_amount = Column(Integer)
    current_amount = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime, nullable=True)
    
    agent = relationship("User", back_populates="session_data")

class Database:
    def __init__(self, db_url='sqlite:///bot.db'):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        return self.Session()

db = Database()
