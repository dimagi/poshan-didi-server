from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from simple_settings import settings
from util import Singleton

Base = declarative_base()


class Timeout(Base):
    __tablename__ = 'timeout_queue'

    id = Column(Integer, primary_key=True)
    chat_src_id = Column(String, nullable=False)
    timeout_time = Column(DateTime, nullable=False)
    valid = Column(Boolean, default=True, nullable=False)


class Escalation(Base):
    __tablename__ = 'nurse_queue'

    id = Column(Integer, primary_key=True)
    chat_src_id = Column(String)
    first_name = Column(String)
    msg_txt = Column(String)
    pending = Column(Boolean, default=True)
    state_name_when_escalated = Column(String)
    escalated_time = Column(DateTime)
    replied_time = Column(DateTime)

# TODO: Should the primary key be the chat_id?
# TODO: Should we get rid of the linking between User and Message? We don't
# use it aywhere and I'm a bit nervous using it would do unpredictable things


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    test_user = Column(Boolean)
    track = Column(String)
    aww = Column(String)
    aww_number = Column(String)
    awc_code = Column(String)
    child_name = Column(String)
    child_gender = Column(String(1))
    child_birthday = Column(DateTime)
    phone_number = Column(String)
    current_state = Column(String)
    current_state_name = Column(String)
    registration_date = Column(DateTime)
    next_module = Column(Integer, default=1, nullable=False)
    started = Column(Boolean, default=False, nullable=False)
    first_msg_date = Column(DateTime)
    chat_id = Column(String, unique=True, index=True)

    cohort = Column(Integer, default=-1, nullable=False)

    messages = relationship(
        'Message', order_by='Message.server_time', back_populates='user')

    def to_dict(self):
        return {col.name: getattr(self, col.name) for col in self.__table__.columns}


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    msg = Column(String)
    server_time = Column(DateTime)
    chat_id = Column(String, index=True)
    source = Column(String)
    # Name of the state when a message was received from the user
    state = Column(String)

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

    def get_state_name_from_chat_id(self, chat_id):
        user = self.session.query(User).filter_by(chat_id=str(chat_id)).first()
        try:
            return user.current_state_name
        except AttributeError:
            return '<unregistered_user>'

    def insert(self, obj):
        if type(obj) is list:
            self.session.add_all(obj)
        else:
            self.session.add(obj)
        self.session.commit()

    def nurse_queue_pending(self):
        return bool(self.session.query(Escalation.pending).filter_by(pending=True).first())

    def get_nurse_queue_first_pending(self):
        return self.session.query(Escalation).filter_by(pending=True).order_by(Escalation.escalated_time.asc()).first()

    def nurse_queue_mark_answered(self, chat_id):
        self.session.query(Escalation).filter_by(
            chat_src_id=chat_id, pending=True).update({'pending': False, 'replied_time': datetime.utcnow()})
        self.commit()
