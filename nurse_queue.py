from collections import OrderedDict

"""
Small wrapper around OrderedDict that provides some additional
appliocation-specific functionality
"""
import logging

from simple_settings import settings

from db import Database
from send import _log_msg
from util import Singleton


class Msg():
    def __init__(self, first_name, chat_src, msg):
        self.chat_src = chat_src
        self.first_name = first_name
        self.msg = msg


# Yes, another Singleton. IT'S FINE.
class NurseQueue(metaclass=Singleton):
    def __init__(self):
        self.__the_queue = OrderedDict()
        self.__pending = False
        self.__current_msg_to_nurse = None
        self.__logger = logging.getLogger(__name__)

    def append(self, key, data):
        # We care not about performance
        try:
            self.__the_queue[key].append(data)
        except KeyError:
            self.__the_queue[key] = [data]

    def popleft(self):
        # last=false because this is a queue not a stack
        # returns a tuple: key, [msg,msg,msg]
        return self.__the_queue.popitem(last=False)

    def __len__(self):
        return len(self.__the_queue)

    @property
    def pending(self):
        return self.__pending

    @pending.setter
    def pending(self, val):
        self.__pending = val

    @property
    def current_msg_to_nurse(self):
        return self.__current_msg_to_nurse

    def mark_answered(self, context):
        self.__pending = False
        self.check_nurse_queue(context)

    def check_nurse_queue(self, context, new_msg=None):
        """Check if the new message is the current client (and send if yes), else add it to the queue"""
        if new_msg is None and len(self) == 0:
            return

        if self.__pending and new_msg.chat_src == self.__current_msg_to_nurse.chat_src:
            context.bot.send_message(
                settings.NURSE_CHAT_ID,
                f'Also from "{new_msg.first_name}" ({new_msg.chat_src}):\n\n'
                f'{new_msg.msg}')
            return
        elif self.__pending:
            # There is a msg currently pending. If we are trying to add a
            # new message, just add it and be done.
            if new_msg is not None:
                self.append(new_msg.chat_src, new_msg)
            return

        # Add messages from (not the active) user to the message queue
        if new_msg is not None:
            self.append(new_msg.chat_src, new_msg)
        self.__logger.info(self.__the_queue)

        # No pending message, but we have a new one added to the queue
        _, msg_list = self.popleft()
        self.__current_msg_to_nurse = msg_list[0]
        nl = '\n'
        msg = (f"The following message(s) are from "
               f"'{self.__current_msg_to_nurse.first_name}' ({self.__current_msg_to_nurse.chat_src})."
               f"Your reply will be forwarded automatically.\n\n"
               f"{nl.join([m.msg for m in msg_list])}")
        _log_msg(msg, 'system', None,
                 state=Database().get_state_name_from_chat_id(
                     self.__current_msg_to_nurse.chat_src),
                 chat_id=settings.NURSE_CHAT_ID)
        context.bot.send_message(
            settings.NURSE_CHAT_ID,
            msg)
        self.__pending = True
