from datetime import datetime
from db import Database, Message


def _log_msg(text, source, update, chat_id=None):
    chat_id = chat_id or update.effective_chat.id
    msg = Message(
        msg=text,
        source=source,
        chat_id=chat_id,
        server_time=datetime.utcnow()
    )
    Database().insert(msg)


def send_text_reply(txt, update, **kwargs):
    _log_msg(txt, 'system', update)
    update.message.reply_text(txt, **kwargs)
