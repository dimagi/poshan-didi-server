from datetime import datetime
from db import Database, Message


def _log_msg(text, source, update, state=None, chat_id=None):
    chat_id = chat_id or update.effective_chat.id
    msg = Message(
        msg=text,
        source=source,
        chat_id=chat_id,
        state=state,
        server_time=datetime.utcnow()
    )
    Database().insert(msg)


def send_text_reply(txt, update, **kwargs):
    _log_msg(txt, 'system', update,
             state=Database().get_state_name_from_chat_id(
                 update.effective_chat.id
             ),
             chat_id=update.effective_chat.id)
    update.message.reply_text(txt, **kwargs)
