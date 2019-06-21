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


def send_image_reply(img, update, state=None, **kwargs):
    state = state or Database().get_state_name_from_chat_id(
        update.effective_chat.id)
    _log_msg(img, 'system', update,
             state=state,
             chat_id=update.effective_chat.id)
    f = open(img, 'rb')
    update.message.reply_photo(f, **kwargs)
    f.close()


def send_text_reply(txt, update, state=None, ** kwargs):
    state = state or Database().get_state_name_from_chat_id(
        update.effective_chat.id)
    _log_msg(txt, 'system', update,
             state=state,
             chat_id=update.effective_chat.id)
    update.message.reply_text(txt, **kwargs)
