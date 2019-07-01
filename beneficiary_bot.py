import os
from datetime import datetime, timedelta
import logging

from simple_settings import settings

import nurse_bot
from customnlu import interpreter, Intent, get_intent
from db import Database, User, Message, Escalation
from send import send_text_reply, send_image_reply, _log_msg
from state_machine import StateMachine


CONFUSED_MSG1 = "Hmm, I didn't quite understand what you're trying to say. Please try again"
CONFUSED_MSG2 = "Let me check into that and get back to you"
CONFUSION_BUFFER_MINUTES = 3

WRONG_INPUT = "I did not quite understand what you are saying. Please try again."
WRONG_INPUT_HI = "मुझे समझ नहीं आया आप क्या कहना चाह। कृपया पुन: प्रयास करें।"

TIMEOUT_TEXT = "Thank you for talking to me. If you want to talk to me again, say hello."
TIMEOUT_TEXT_HI = "मुझसे बात करने के लिए धन्यवाद। यदि आप किसी भी समय बात करना चाहते हैं तो 'हेल्लो' बोलिये!"

# Enable logging
logging.basicConfig(filename=settings.LOG_FILENAME,
                    format=settings.LOG_FORMAT,
                    level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

#################################################
# State machine helper fns
#################################################
#  TODO: get rid of this global statemachine
sm6 = None
sm12 = None


def setup_state_machines():
    global sm6, sm12
    sm6 = StateMachine(settings.FLOW_6_MONTHS, settings.TRANSLATIONS_6_MONTHS)
    sm12 = StateMachine(settings.FLOW_12_MONTHS,
                        settings.TRANSLATIONS_12_MONTHS)


def get_sm_from_track(track):
    if int(track) == 12:
        return sm12
    return sm6


def _get_sm_from_context(context):
    return get_sm_from_track(context.user_data['track'])


#################################################
# State handling
#################################################
def fetch_user_data(chat_id, context):
    user = Database().session.query(User).filter_by(chat_id=str(chat_id)).first()
    if user:
        # https://stackoverflow.com/questions/38987/how-to-merge-two-dictionaries-in-a-single-expression
        logger.info(f'found info for {chat_id}, {user.to_dict()}')
        context.user_data = {**context.user_data, **(user.to_dict())}
        # context.user_data = {**context.user_data, **user._asdict()}
    else:
        logger.info(f'no info found for {chat_id}')
        user = {'aww': 'NONE', 'track': 'NONE', 'aww_number': 'NONE', 'awc_code': 'NONE', 'first_name': 'NONE', 'last_name': 'NONE',
                'child_name': 'NONE', 'child_birthday': 'NONE', 'current_state': 'NONE',
                'current_state_name': 'NONE'}
        context.user_data = {**context.user_data, **user}


def _get_current_state_from_context(context):
    try:
        return context.user_data['current_state'], context.user_data['current_state_name']
    except KeyError:
        return None, None


def get_chat_id(update, context):
    try:
        return f"{context.user_data['first_name']} ({update.effective_chat.id})"
    except KeyError:
        return update.effective_chat.id


def _save_user_state(chat_id, state_id, state_name):
    logger.info(f'setting state to {state_name} for {chat_id}')
    our_user = Database().session.query(User).filter_by(chat_id=str(chat_id)).first()
    our_user.current_state = state_id
    our_user.current_state_name = state_name
    Database().commit()


def _get_menu_for_user(context):
    # msgs, imgs, state_id, state_name
    # THIS is a HACK
    if int(context.user_data['track']) == 6:
        state_name = '1_1_kmm'
    else:
        state_name = '1_1_act'

    sm = _get_sm_from_context(context)
    return sm.get_messages_from_state_name(state_name, context.user_data['child_gender']), sm.get_images_from_state_name(state_name), sm.get_state_id_from_state_name(state_name), state_name

#################################################
# Timeout
#################################################


def timeout(context):
    chat_id = context.job.context["chat_id"]
    logger.info(f'Timeout called for {chat_id}')

    # Reset state
    prior_state = context.job.context['current_state_name']
    _save_user_state(chat_id, None, None)

    # Tell the user
    msg_txt = TIMEOUT_TEXT
    if settings.HINDI:
        msg_txt = TIMEOUT_TEXT_HI
    _log_msg(msg_txt, 'system-timeout', None,
             state=prior_state,
             chat_id=str(chat_id))
    context.bot.send_message(
        chat_id, msg_txt)


def remove_old_timer_add_new(context):
    for j in context.job_queue.get_jobs_by_name(f'timeout_{context.user_data["chat_id"]}'):
        j.schedule_removal()

    context.user_data['job_timeout'] = context.job_queue.run_once(
        timeout, timedelta(minutes=settings.STATE_TIMEOUT_MINUTES),
        context=context.user_data,
        name=f'timeout_{context.user_data["chat_id"]}')


#################################################
# Message sending and prep
#################################################
def replace_template(msg, context):
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


def prepend_img_path(img):
    return os.path.join('data', 'images', img)


#################################################
# Telegram bot processing new messages
#################################################
def _process_unknown(update, context, current_state_id, state_name):
    now = int(datetime.utcnow().timestamp())
    msg = CONFUSED_MSG1
    state_id = current_state_id
    try:
        last_confused = context.user_data['last_confused']
        if now - last_confused < 60*CONFUSION_BUFFER_MINUTES:
            msg = CONFUSED_MSG2
            _, state_name = _get_current_state_from_context(context)
            new_escalation = Escalation(
                chat_src_id=update.effective_chat.id,
                first_name=context.user_data['first_name'],
                msg_txt=update.message.text,
                pending=True,
                escalated_time=datetime.utcnow(),
                state_name_when_escalated=state_name
            )
            Database().insert(new_escalation)
            nurse_bot._check_nurse_queue(context)
            # state_id = None
            # state_name = '<None>'
    except KeyError:
        pass
    context.user_data['last_confused'] = now
    return [msg], state_id, state_name


def handle_echo(update, context):
    intent = get_intent(update.message.text)

    # Get the correct state machine
    sm = _get_sm_from_context(context)

    if intent == Intent.UNKNOWN or (int(intent) < 1 or int(intent) > 10):
        if settings.HINDI:
            send_text_reply("मुझे खेद है कि मुझे यह समझ में नहीं आया। यह 1 से 10 के बीच एक भी अंक नहीं है। कृपया 1 से 10 के बीच का कोई एक अंक लिखें।",
                            update)
        else:
            send_text_reply(
                "I am sorry I did not understand that. It is not a single digit number between 1 to 10. Please enter one digit between 1 to 10.",
                update)
    else:
        if settings.HINDI:
            send_text_reply(f'आपने {str(int(intent))} नंबर दर्ज किया है।',
                            update)
        else:
            send_text_reply(
                f'You have said: {str(int(intent))}',
                update)


def process_user_input(update, context):
    """Handle a user message."""
    logger.info(f'trying to get info for {update.effective_chat.id}')
    fetch_user_data(update.effective_chat.id, context)
    logger.info(f'ending user dict is: {context.user_data}')
    current_state_id, state_name = _get_current_state_from_context(context)
    logger.info(f'fetched the following: {current_state_id}, {state_name}')
    _log_msg(update.message.text, 'user', update, state=state_name)
    logger.info(
        f'[{get_chat_id(update, context)}] - msg received: {update.message.text}')

    # Special case for echos
    if state_name == 'echo':
        return handle_echo(update, context)

    # First, set a timeout
    remove_old_timer_add_new(context)

    intent = get_intent(update.message.text)

    # Get the correct state machine
    sm = _get_sm_from_context(context)

    imgs = []
    terminal = False
    if intent == Intent.UNKNOWN:
        logger.warn(
            f'[{get_chat_id(update, context)}] - intent: {intent} msg: {update.message.text}')
        msgs, state_id, state_name = _process_unknown(
            update, context, current_state_id, state_name)
    else:
        logger.info(
            f'[{get_chat_id(update, context)}] - intent: {intent} msg: {update.message.text}')

        try:
            if current_state_id is None:
                msgs, imgs, state_id, state_name = _get_menu_for_user(context)
                _save_user_state(update.effective_chat.id,
                                 state_id, state_name)
                msgs = [replace_template(m, context) for m in msgs]
                for msg in msgs:
                    send_text_reply(msg, update)
                if imgs:
                    for img in imgs:
                        send_image_reply(prepend_img_path(img), update)
            else:
                msgs, imgs, state_id, state_name, terminal = sm.get_msg_and_next_state(
                    current_state_id, intent, context.user_data['child_gender'])
        except ValueError:
            # This is a state transition that doesn't exist (e.g., they typed 6
            # when the menu is only 1-5)
            msgs = [WRONG_INPUT]
            if settings.HINDI:
                msgs = [WRONG_INPUT_HI]
            # Repeat our message.
            msgs = msgs + sm.get_messages_from_state_name(
                state_name, context.user_data['child_gender'])
            state_id = current_state_id

    logger.info(
        f'[{get_chat_id(update, context)}] - current state: {current_state_id} -> next state: {state_id}')

    # logger.info(f'[{update.effective_chat.id}] - next state: {state.msg_id}')
    context.user_data['current_state'] = state_id
    _save_user_state(update.effective_chat.id, state_id, state_name)
    msgs = [replace_template(m, context) for m in msgs]
    for msg in msgs:
        send_text_reply(msg, update)
    if imgs:
        for img in imgs:
            send_image_reply(prepend_img_path(img), update)

    # Such a HACK
    if terminal:
        msgs, imgs, state_id, state_name = _get_menu_for_user(context)
        _save_user_state(update.effective_chat.id, state_id, state_name)
        msgs = [replace_template(m, context) for m in msgs]
        for msg in msgs:
            send_text_reply(msg, update)
        if imgs:
            for img in imgs:
                send_image_reply(prepend_img_path(img), update)
