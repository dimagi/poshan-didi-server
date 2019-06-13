#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poshan Didi!
"""

from datetime import datetime
import logging
import requests
from collections import OrderedDict

# from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove)

from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from simple_settings import settings

from registration import registration_conversation
from nurse_queue import NurseQueue, Msg
from state_machine import StateMachine
from send import send_text_reply, _log_msg
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
        return context.user_data['current_state']
    except KeyError:
        return None

# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.


def _process_unknown(update, context, current_state):
    now = int(datetime.utcnow().timestamp())
    msg = CONFUSED_MSG1
    state = current_state
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
            state = None
    except KeyError:
        pass
    context.user_data['last_confused'] = now
    return msg, state


def get_msg_id(state):
    if state:
        return state.msg_id
    return None


def _fetch_user_data(chat_id, context):
    result = requests.get(
        f'{settings.API_SERVER_ADDRESS}/api/v1/user/{chat_id}')
    try:
        user = result.json()[0]
    except Exception:
        logger.error(f'Unable to find user data for {chat_id}. URL: '
                     f'{settings.API_SERVER_ADDRESS}/api/v1/user/{chat_id}\n'
                     f'Returned value is not valid JSON, using a blank user. Full response:\n'
                     f'{result.text}')
        user = {'aww': 'NONE', 'first_name': 'NONE', 'last_name': 'NONE',
                'child_name': 'NONE', 'child_birthday': 'NONE'}
    # do a dict merge thing  instead
    context.user_data['aww'] = user['aww']
    context.user_data['first_name'] = user['first_name']
    context.user_data['last_name'] = user['last_name']
    context.user_data['child_name'] = user['child_name']
    context.user_data['child_birthday'] = user['child_birthday']


def _replace_template(msg, context):
    return msg.replace("[child\u2019s name]", context.user_data['child_name'])


def process_user_input(update, context):
    """Echo the user message."""
    _log_msg(update.message.text, 'user', update)
    _fetch_user_data(update.effective_chat.id, context)
    logger.info(
        f'[{get_chat_id(update, context)}] - msg received: {update.message.text}')

    current_state = _get_current_state_from_context(context)
    intent = get_intent(update.message.text)

    if intent == Intent.UNKNOWN:
        logger.warn(
            f'[{get_chat_id(update, context)}] - intent: {intent} msg: {update.message.text}')
        msg, state = _process_unknown(update, context, current_state)
    else:
        logger.info(
            f'[{get_chat_id(update, context)}] - intent: {intent} msg: {update.message.text}')
        msg, state = sm.get_msg_and_next_state(current_state, intent)

    logger.info(
        f'[{get_chat_id(update, context)}] - current state: {get_msg_id(current_state)} -> next state: {get_msg_id(state)}')

    # logger.info(f'[{update.effective_chat.id}] - next state: {state.msg_id}')
    context.user_data['current_state'] = state
    msg = _replace_template(msg, context)
    send_text_reply(msg, update)


def process_nurse_input(update, context):
    nq = NurseQueue()

    logger.info(
        f'[{get_chat_id(update, context)}] - NURSE msg received: {update.message.text}')

    if not nq.pending:
        _log_msg(update.message.text, 'nurse', update)
        send_text_reply(
            "You are the nurse and there are no pending messages.", update)
        logger.info(
            f'[{get_chat_id(update, context)}] - no pending nurse messages....')
        return

    _log_msg(update.message.text, 'nurse', update,
             chat_id=nq.current_msg_to_nurse.chat_src)

    context.bot.send_message(
        nq.current_msg_to_nurse.chat_src, update.message.text)
    nq.pending = False
    nq.check_nurse_queue(context)


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


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
