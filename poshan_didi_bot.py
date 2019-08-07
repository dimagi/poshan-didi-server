#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Poshan Didi!
"""

import logging
import logging.handlers

import beneficiary_bot
import nurse_bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from simple_settings import settings
from registration import registration_conversation

# Enable logging
logging.basicConfig(filename=settings.LOG_FILENAME,
                    format=settings.LOG_FORMAT,
                    level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

handler = logging.handlers.RotatingFileHandler(
    settings.LOG_FILENAME,
    maxBytes=10*1024*1024,
    backupCount=100
)

logger.addHandler(handler)

# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.

def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Start the bot."""
    beneficiary_bot.setup_state_machines()

    # Create the Updater and pass it the bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    updater = Updater(settings.TELEGRAM_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Add the regsitration conversation, which handles the /start command
    dp.add_handler(registration_conversation)

    # Add a nurse command to skip the current escalated message 
    # (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('noreply', nurse_bot.skip,
                                  Filters.chat(settings.NURSE_CHAT_ID)))
    
    # Add a nurse command to set state for a user (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('state', nurse_bot.set_state,
                                  Filters.chat(settings.NURSE_CHAT_ID)))

    # Add a nurse command to set state for a user (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('state', nurse_bot.set_super_state,
                                  Filters.chat(settings.GOD_MODE)))

    # Add a nurse command to set state for a user (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('send_next_modules', nurse_bot.send_next_modules,
                                  Filters.chat(settings.GOD_MODE)))

    # Add a nurse command to set state for a user (only allow the nurse to access this command)
    dp.add_handler(CommandHandler('vhnd', nurse_bot.send_vhnd_reminder,
                                  Filters.chat(settings.GOD_MODE)))

    # on non-command i.e., a normal message message - process_user_input the
    # message from Telegram. Use different handlers for the purse and user
    # messages
    dp.add_handler(MessageHandler(
        (Filters.text & (~ Filters.chat(settings.NURSE_CHAT_ID))), beneficiary_bot.process_user_input))
    dp.add_handler(MessageHandler(
        (Filters.text & Filters.chat(settings.NURSE_CHAT_ID)), nurse_bot.process_nurse_input))

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
