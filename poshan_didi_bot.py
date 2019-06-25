#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poshan Didi!
"""

from datetime import datetime
import logging
import os
import requests
from collections import OrderedDict

# from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove)

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from simple_settings import settings

from db import Database, User, Message

from registration import registration_conversation
from nurse_queue import NurseQueue, Msg
from state_machine import StateMachine
from send import send_text_reply, send_image_reply, _log_msg
from customnlu import interpreter, Intent, get_intent


#  TODO: get rid of this global statemachine
sm = None

CONFUSED_MSG1 = "Hmm, I didn't quite understand what you're trying to say. Please try again"
CONFUSED_MSG2 = "Let me check into that and get back to you"
CONFUSION_BUFFER_MINUTES = 3

# Enable logging
logging.basicConfig(filename=settings.LOG_FILENAME,
                    format=settings.LOG_FORMAT,
                    level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


def get_chat_id(update, context):
    try:
        return f"{context.user_data['first_name']} ({update.effective_chat.id})"
    except KeyError:
        return update.effective_chat.id


# TODO: get rid of global variable?
def setup_state_machine():
    global sm
    sm = StateMachine(settings.MAIN_FLOW, settings.TRANSLATIONS_CSV)


def _get_current_state_from_context(context):
    try:
        return context.user_data['current_state_id'], context.user_data['current_state_name']
    except KeyError:
        return None

# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.


def _process_unknown(update, context, current_state_id, state_name):
    now = int(datetime.utcnow().timestamp())
    msg = CONFUSED_MSG1
    state_id = current_state_id
    try:
        last_confused = context.user_data['last_confused']
        if now - last_confused < 60*CONFUSION_BUFFER_MINUTES:
            msg = CONFUSED_MSG2

            NurseQueue().check_nurse_queue(
                context,
                Msg(
                    context.user_data['first_name'],
                    update.effective_chat.id,
                    update.message.text))
            # state_id = None
            # state_name = '<None>'
    except KeyError:
        pass
    context.user_data['last_confused'] = now
    return [msg], state_id, state_name


def _save_user_state(chat_id, state_id, state_name):
    logger.info(f'setting state to {state_name} for {chat_id}')
    our_user = Database().session.query(User).filter_by(chat_id=chat_id).first()
    our_user.current_state = state_id
    our_user.current_state_name = state_name
    Database().commit()


def _fetch_user_data(chat_id, context):
    try:
        user = Database().session.query(
            User.first_name,
            User.last_name,
            User.chat_id,
            User.child_birthday,
            User.child_name,
            User.current_state,
            User.current_state_name,
            User.aww,
            User.track,
            User.aww_number,
            User.awc_code).filter_by(chat_id=chat_id).first()
    except:
        logger.error(
            f'Unable to find user data for {chat_id}. Or, multiple entries for that chat_id')
        user = {'aww': 'NONE', 'track': 'NONE', 'aww_number': 'NONE', 'awc_code': 'NONE', 'first_name': 'NONE', 'last_name': 'NONE',
                'child_name': 'NONE', 'child_birthday': 'NONE', 'current_state': 'NONE',
                'current_state_name': 'NONE'}

    # do a dict merge thing instead?
    context.user_data['aww'] = user.aww
    context.user_data['track'] = user.track
    context.user_data['aww_number'] = user.aww_number
    context.user_data['awc_code'] = user.awc_code
    context.user_data['first_name'] = user.first_name
    context.user_data['last_name'] = user.last_name
    context.user_data['child_name'] = user.child_name
    context.user_data['current_state_id'] = user.current_state
    context.user_data['current_state_name'] = user.current_state_name
    context.user_data['child_birthday'] = user.child_birthday


def _replace_template(msg, context):
    repl = {
        '[child name]': context.user_data['child_name'],
        '[बच्चे का नाम]': context.user_data['child_name'],
        '[AWW name]': context.user_data['aww'],
        '[AWW नाम]': context.user_data['aww'],
        '[mother name]': context.user_data['first_name'],
        '[AWW phone number]': context.user_data['aww_number'],
        '[AWW फोन नंबर]': context.user_data['aww_number'],
    }
    for initial, word in repl.items():
        msg = msg.replace(initial, word)
    return msg


def _prepend_img_path(img):
    return os.path.join('data', 'images', img)


def process_user_input(update, context):
    """Echo the user message."""
    _fetch_user_data(update.effective_chat.id, context)
    current_state_id, state_name = _get_current_state_from_context(context)
    _log_msg(update.message.text, 'user', update, state=state_name)
    logger.info(
        f'[{get_chat_id(update, context)}] - msg received: {update.message.text}')

    intent = get_intent(update.message.text)

    imgs = None
    if intent == Intent.UNKNOWN:
        logger.warn(
            f'[{get_chat_id(update, context)}] - intent: {intent} msg: {update.message.text}')
        msgs, state_id, state_name = _process_unknown(
            update, context, current_state_id, state_name)
    else:
        logger.info(
            f'[{get_chat_id(update, context)}] - intent: {intent} msg: {update.message.text}')
        msgs, imgs, state_id, state_name = sm.get_msg_and_next_state(
            current_state_id, intent)

    logger.info(
        f'[{get_chat_id(update, context)}] - current state: {current_state_id} -> next state: {state_id}')

    # logger.info(f'[{update.effective_chat.id}] - next state: {state.msg_id}')
    context.user_data['current_state_id'] = state_id
    _save_user_state(update.effective_chat.id, state_id, state_name)
    msgs = [_replace_template(m, context) for m in msgs]
    for msg in msgs:
        send_text_reply(msg, update)
    if imgs:
        for img in imgs:
            send_image_reply(_prepend_img_path(img), update)


def _check_pending(update, context, none_pending_msg):
    nq = NurseQueue()
    if not nq.pending:
        send_text_reply(none_pending_msg, update)
        logger.info(
            f'[{get_chat_id(update, context)}] - no pending nurse messages....')
        return False
    return True


def _send_message_to_queue(update, context, msgs_txt):
    """Send msg_text to the user at teh top of the nurse queue
    This does not update the queue (in case we want to send multiple messages.
    This will, however, log everything correctly"""
    chat_id = NurseQueue().current_msg_to_nurse.chat_src
    _fetch_user_data(chat_id, context)

    for msg_txt in msgs_txt:
        # Log the message from nurse to the user
        _log_msg(msg_txt, 'nurse', update,
                 state=Database().get_state_name_from_chat_id(chat_id),
                 chat_id=chat_id)
        # And send it
        context.bot.send_message(
            chat_id, _replace_template(msg_txt, context))


def _send_message_to_chat_id(update, context, chat_id, msgs_txt):
    """Send msg_text to the user at teh top of the nurse queue
    This does not update the queue (in case we want to send multiple messages.
    This will, however, log everything correctly"""
    _fetch_user_data(chat_id, context)

    for msg_txt in msgs_txt:
        # Log the message from nurse to the user
        _log_msg(msg_txt, 'GOD', update,
                 state=Database().get_state_name_from_chat_id(chat_id),
                 chat_id=chat_id)
        # And send it
        context.bot.send_message(
            chat_id, _replace_template(msg_txt, context))


def process_nurse_input(update, context):
    if NurseQueue().current_msg_to_nurse is not None:
        chat_id = NurseQueue().current_msg_to_nurse.chat_src
    else:
        chat_id = update.effective_chat.id
    # Save the message the nurse sent in.
    _log_msg(update.message.text, 'nurse', update,
             state=Database().get_state_name_from_chat_id(chat_id))
    logger.info(
        f'[{get_chat_id(update, context)}] - NURSE msg received: {update.message.text}')

    # if there are no meding messages, we are done.
    if not _check_pending(update, context, "You are the nurse and there are no pending messages."):
        return

    # Log and send message from nurse to the specific chat ID, then check if
    # there are more in the queue
    _send_message_to_queue(update, context, [update.message.text])
    NurseQueue().mark_answered(context)


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def _set_user_state(update, chat_id, new_state):
    # Set the state for the user manually
    our_user = Database().session.query(User).filter_by(chat_id=chat_id).first()
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
    chat_id = NurseQueue().current_msg_to_nurse.chat_src
    _log_msg(update.message.text, 'nurse', update,
             state=Database().get_state_name_from_chat_id(chat_id))

    # Ensure we have pending messages
    if not _check_pending(update, context,
                          "The state command can only be used when there is a pending message. There are currently no pending messages"):
        return

    # Check syntax of the command
    try:
        cmd_parts = update.message.text.split()
        if len(cmd_parts) != 2:
            raise Exception()
        new_state = cmd_parts[1]
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

    _send_message_to_queue(
        update, context, sm.get_messages_from_state_name(new_state))

    # Tell the nurse and check the queue
    send_text_reply(
        f"Ok. State successfully set to {new_state} and message sent to the user.", update)
    NurseQueue().mark_answered(context)


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

    _send_message_to_chat_id(
        update, context, chat_id,
        sm.get_messages_from_state_name(new_state))

    # Tell the nurse and check the queue
    send_text_reply(
        f"Ok. State successfully set to {new_state} and message sent to the user.", update)
    # NurseQueue().mark_answered(context)


def main():
    """Start the bot."""
    setup_state_machine()

    # Create the Updater and pass it the bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    updater = Updater(settings.TELEGRAM_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Add the regsitration conversation, which handles the /start command
    dp.add_handler(registration_conversation)

    # Add a nurse command to set state for a user (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('state', set_state,
                                  Filters.chat(settings.NURSE_CHAT_ID)))

    # Add a nurse command to set state for a user (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('state', set_super_state,
                                  Filters.chat(settings.GOD_MODE)))

    # on non-command i.e., a normal message message - process_user_input the
    # message from Telegram. Use different handlers for the purse and user
    # messages
    dp.add_handler(MessageHandler(
        (Filters.text & (~ Filters.chat(settings.NURSE_CHAT_ID))), process_user_input))
    dp.add_handler(MessageHandler(
        (Filters.text & Filters.chat(settings.NURSE_CHAT_ID)), process_nurse_input))

    # log all errors
    dp.add_error_handler(error)
    logger.info(
        '************************** POSHAN DIDI HAS RETURNED **************************')

    # Start the Bot.
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
