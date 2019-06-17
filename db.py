from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from simple_settings import settings
from util import Singleton

Base = declarative_base()


# TODO: Should the primary key be the chat_id?
# TODO: Should we get rid of the linking between User and Message? We don't
# use it aywhere and I'm a bit nervous using it would do unpredictable things
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    aww = Column(String)
    child_name = Column(String)
    child_birthday = Column(DateTime)
    phone_number = Column(String)
    current_state = Column(String)
    current_state_name = Column(String)
    chat_id = Column(String, unique=True, index=True)

    messages = relationship(
        'Message', order_by='Message.server_time', back_populates='user')


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    msg = Column(String)
    server_time = Column(DateTime)
    chat_id = Column(String, index=True)
    source = Column(String)

    user = relationship('User', back_populates='messages')


# Lots of people have lots of opinions on Singletons. This is research code,
# let's not get righteous.
class Database(metaclass=Singleton):
    def __init__(self):
        # self.engine = create_engine('sqlite:///:memory:')
        self.engine = create_engine(settings.DB_SQLALCHEMY_CONNECTION)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.reset_db()

    def commit(self):
        self.session.commit()

    def reset_db(self):
        Base.metadata.create_all(self.engine)

    def insert(self, obj):
        if type(obj) is list:
            self.session.add_all(obj)
        else:
            self.session.add(obj)
        self.session.commit()
