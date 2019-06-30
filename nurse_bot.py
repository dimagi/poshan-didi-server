from datetime import datetime
import logging

# from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from simple_settings import settings

import beneficiary_bot
from db import Database, User, Message, Escalation
from send import send_text_reply, send_image_reply, _log_msg

# Enable logging
logging.basicConfig(filename=settings.LOG_FILENAME,
                    format=settings.LOG_FORMAT,
                    level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


#################################################
# Nurse queue
#################################################
def _check_nurse_queue(context):
    first_pending = Database().get_nurse_queue_first_pending()
    try:
        relevant_messages = Database().session.query(
            Escalation
        ).filter_by(pending=True, chat_src_id=first_pending.chat_src_id)
    except AttributeError:
        # No pending messages
        return
    for msg in relevant_messages:
        _log_msg(msg.msg_txt, 'system-unsent', None, msg.state_name_when_escalated,
                 chat_id=settings.NURSE_CHAT_ID)
        msg.replied_time = datetime.utcnow()

    nl = '\n'
    msg = (f"The following message(s) are from "
           f"'{first_pending.first_name}' ({first_pending.chat_src_id})."
           f"Your reply will be forwarded automatically.\n\n"
           f"{nl.join([m.msg_txt for m in relevant_messages])}")
    context.bot.send_message(
        settings.NURSE_CHAT_ID,
        msg
    )
    Database().commit()


def _check_pending(update, context, none_pending_msg):
    if not Database().nurse_queue_pending():
        send_text_reply(none_pending_msg, update)
        logger.info(
            f'[{beneficiary_bot.get_chat_id(update, context)}] - no pending nurse messages....')
        return False
    return True


def _send_message_to_queue(update, context, msgs_txt):
    """Send msg_text to the user at the top of the nurse queue
    This does not update the queue (in case we want to send multiple messages.
    This will, however, log everything correctly"""
    escalation = Database().get_nurse_queue_first_pending()
    beneficiary_bot.fetch_user_data(escalation.chat_src_id, context)

    for msg_txt in msgs_txt:
        # Log the message from nurse to the user
        _log_msg(msg_txt, 'nurse', update,
                 state=Database().get_state_name_from_chat_id(escalation.chat_src_id),
                 chat_id=str(escalation.chat_src_id))
        # And send it
        context.bot.send_message(
            escalation.chat_src_id, beneficiary_bot.replace_template(msg_txt, context))


def _send_message_to_chat_id(update, context, chat_id, msgs_txt):
    """Send msg_text to a specific chat_id from GOD mode."""
    beneficiary_bot.fetch_user_data(chat_id, context)

    for msg_txt in msgs_txt:
        # Log the message from nurse to the user
        _log_msg(msg_txt, 'GOD', update,
                 state=Database().get_state_name_from_chat_id(chat_id),
                 chat_id=str(chat_id))
        # And send it
        context.bot.send_message(
            chat_id, beneficiary_bot.replace_template(msg_txt, context))


#################################################
# State setting
#################################################
def _set_user_state(update, chat_id, new_state):
    # Set the state for the user manually
    our_user = Database().session.query(User).filter_by(chat_id=str(chat_id)).first()
    sm = beneficiary_bot.get_sm_from_track(our_user.track)
    try:
        state_id = sm.get_state_id_from_state_name(new_state)
    except ValueError:
        send_text_reply(
            f"Usage details: /state <new_state_name>\n '{new_state}' not recognized as a valid state.", update)
        return False
    our_user.current_state = state_id
    our_user.current_state_name = new_state
    Database().commit()
    return True


def set_state(update, context):
    # Save the mssage the nurse sent in
    logger.warning('Set state called!')
    current_msg = Database().get_nurse_queue_first_pending()
    try:
        chat_id = current_msg.chat_src_id
    except AttributeError:
        chat_id = update.effective_chat.id
    _log_msg(update.message.text, 'nurse', update,
             state=Database().get_state_name_from_chat_id(chat_id))

    # Ensure we have pending messages
    if not _check_pending(update, context,
                          "The state command can only be used when there is a pending message. There are currently no pending messages"):
        return

    # Check syntax of the command
    try:
        cmd_parts = update.message.text.split()
        if len(cmd_parts) < 2:
            raise Exception()
        new_state = ''.join(cmd_parts[1:])
    except:
        send_text_reply(
            "Usage details: /state <new_state_name>", update)
        return

    # Update the DB with the correct message text
    if not _set_user_state(update,
                           chat_id,
                           new_state):
        # failed to find the state the nurse requested
        return

    our_user = Database().session.query(User).filter_by(chat_id=str(chat_id)).first()
    sm = beneficiary_bot.get_sm_from_track(our_user.track)
    _send_message_to_queue(
        update, context, sm.get_messages_from_state_name(new_state, our_user.child_gender))

    # Tell the nurse and check the queue
    send_text_reply(
        f"Ok. State successfully set to {new_state} and message sent to the user.", update)
    Database().nurse_queue_mark_answered(current_msg.chat_src_id)
    _check_nurse_queue(context)


def set_super_state(update, context):
    # Save the mssage the nurse sent in
    logger.warning('Set SUPER state called in GOD mode!')
    _log_msg(update.message.text, 'GOD', update)

    # Check syntax of the command
    try:
        cmd_parts = update.message.text.split()
        if len(cmd_parts) != 3:
            raise Exception()
        chat_id = cmd_parts[1]
        new_state = cmd_parts[2]
    except:
        send_text_reply(
            "Usage details for GOD mode: /state <chat_id> <new_state_name>", update)
        return

    # Update the DB with the correct message text
    if not _set_user_state(update,
                           chat_id,
                           new_state):
        # failed to find the state the nurse requested
        return

    our_user = Database().session.query(User).filter_by(chat_id=str(chat_id)).first()
    sm = beneficiary_bot.get_sm_from_track(our_user.track)
    _send_message_to_chat_id(
        update, context, chat_id,
        sm.get_messages_from_state_name(new_state, our_user.child_gender))

    # Tell the nurse and check the queue
    send_text_reply(
        f"Ok. State successfully set to {new_state} and message sent to the user.", update)
    _check_nurse_queue(context)


#################################################
# Telegram bot processing new messages
#################################################
def process_nurse_input(update, context):
    current_msg = Database().get_nurse_queue_first_pending()
    try:
        chat_id = current_msg.chat_src_id
    except AttributeError:
        chat_id = update.effective_chat.id
    # Save the message the nurse sent in.
    _log_msg(update.message.text, 'nurse', update,
             state=Database().get_state_name_from_chat_id(chat_id))
    logger.info(
        f'[{beneficiary_bot.get_chat_id(update, context)}] - NURSE msg received: {update.message.text}')

    # if there are no meding messages, we are done.
    if not _check_pending(update, context, "You are the nurse and there are no pending messages."):
        return

    # Log and send message from nurse to the specific chat ID, then check if
    # there are more in the queue
    _send_message_to_queue(update, context, [update.message.text])
    Database().nurse_queue_mark_answered(current_msg.chat_src_id)
    _check_nurse_queue(context)
