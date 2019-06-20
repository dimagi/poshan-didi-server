from datetime import datetime

from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler)
from db import User, Database
from send import send_text_reply, _log_msg
from customnlu import interpreter, get_intent, Intent

# Define the states
CONFIRM_NAME, ASK_NAME, ASK_CHILD_NAME, ASK_CHILD_BIRTHDAY, PHONE_NUMBER, AWW_LIST, AWC_CODE = range(
    7)


def cancel(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    send_text_reply('cancel called', update, state='registration')
    pass


def start(update, context):
    # TODO: Update this once we are ready to launch?
    send_text_reply(
        'Hello and welcome. My name is Poshan Didi and I am currently under development.', update, state='registration')

    send_text_reply(
        f'Can I call you {update.message.from_user.first_name}?', update, state='registration')
    return CONFIRM_NAME


def _save_name(update, context, name):
    # Don't save because we will have saved input before this is called.
    # _log_msg(update.message.text, 'user', update, state='registration')
    context.user_data['preferred_name'] = name
    send_text_reply(
        f'Ok, thank you {name}. Please tell me what I should call your child (just a first name is fine).', update, state='registration')
    return ASK_CHILD_NAME


def confirm_name(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    intent = get_intent(update.message.text)
    if intent == Intent.YES:
        return _save_name(update, context, update.message.from_user.first_name)
    elif intent == Intent.NO:
        send_text_reply(
            'Ok, no problem. What would you like me to call you (just a first name is fine)?', update, state='registration')
        return ASK_NAME

    send_text_reply(
        f"I didn't quite get that. Please respond with 'yes' or 'no'. Can I call you {update.message.from_user.first_name}?", update, state='registration')
    return CONFIRM_NAME


def ask_name(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    return _save_name(update, context, update.message.text)


def ask_child_name(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    name = context.user_data['preferred_name']
    context.user_data['child_name'] = update.message.text
    send_text_reply(
        f'Ok, thank you {name}--I will refer to your child as {update.message.text}.\n\nAlmost done--just a few more questions. '
        f'What is the birthday for {update.message.text}? Please enter in this format: YYYY-MM-DD', update, state='registration')
    return ASK_CHILD_BIRTHDAY


def ask_child_birthday(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    context.user_data['child_birthday'] = update.message.text
    send_text_reply(
        f'Got it. What is your phone number? Please enter it in the following format: +91dddddddddd, where each d is a number', update, state='registration')
    return PHONE_NUMBER


def phone_number(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    # Our regex lets the users put in white space, so strip it all out
    # (this doesnt actually matter, but is nice)
    context.user_data['phone_number'] = update.message.text.replace(' ', '')
    send_text_reply(
        f'Great! What is the name of the AWW here?', update, state='registration')
    return AWW_LIST


def ask_awc_code(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    context.user_data['aww'] = update.message.text
    send_text_reply(
        f'Thanks! Last question: what is the AWC code?', update, state='registration')
    return AWC_CODE


def thanks(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    context.user_data['awc_code'] = update.message.text
    # SAVE THE USER
    new_user = User(
        chat_id=update.effective_chat.id,
        first_name=context.user_data['preferred_name'],
        last_name=update.message.from_user.last_name,
        phone_number=context.user_data['phone_number'],
        child_name=context.user_data['child_name'],
        child_birthday=datetime.strptime(
            context.user_data['child_birthday'], '%Y-%m-%d'),
        aww=context.user_data['aww'],
        awc_code=context.user_data['awc_code']
    )
    Database().insert(new_user)
    send_text_reply(
        "Thank you! You're all registered. Just wait for your first message, which should come at some point in the next 7 days", update, state='registration')
    return ConversationHandler.END


registration_conversation = ConversationHandler(
    entry_points=[CommandHandler('start', start)],

    states={
        CONFIRM_NAME: [MessageHandler(Filters.text, confirm_name)],

        ASK_NAME: [MessageHandler(Filters.text, ask_name)],

        ASK_CHILD_NAME: [MessageHandler(Filters.text, ask_child_name)],

        ASK_CHILD_BIRTHDAY: [MessageHandler(Filters.regex('^201[8,9]-[0,1][0-9]-[0,1,2,3][0-9]$'), ask_child_birthday)],

        PHONE_NUMBER: [MessageHandler(Filters.regex('^\+9\s*1\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*$'), phone_number)],

        AWW_LIST: [MessageHandler(Filters.text, ask_awc_code)],

        AWC_CODE: [MessageHandler(Filters.text, thanks)],
    },

    fallbacks=[CommandHandler('cancel', cancel)]
)
