import csv
import os
import glob
from datetime import datetime, timedelta
import logging

from simple_settings import settings

import nurse_bot
from customnlu import interpreter, Intent, get_intent
from db import Database, User, Message, Escalation
from send import send_text_reply, send_image_reply, _log_msg
from state_machine import StateMachine


# CONFUSED_MSG1 = "Hmm, I didn't quite understand what you're trying to say. Please try again"
# CONFUSED_MSG2 = "Let me check into that and get back to you"
# CONFUSION_BUFFER_MINUTES = 3

ESCALATE_TEXT = 'Let me check into that and get back to you.'
ESCALATE_TEXT_HI = 'मुझे इस बारे में थोड़ी जानकारी इकठ्ठा कर के आपको थोड़ी देर में बताती हूँ।'

WRONG_INPUT = "I did not quite understand what you are saying. Please try again."
WRONG_INPUT_HI = "मुझे आप जो कह रहे हैं वो समझ नहीं आया, कृपया फिर से प्रयास करें।"

TIMEOUT_TEXT = "Thank you for talking to me. If you want to talk to me again, say hello."
TIMEOUT_TEXT_HI = "मुझसे बात करने के लिए धन्यवाद। यदि आप किसी भी समय बात करना चाहते हैं तो 'हेल्लो' बोलिये!"

GLOBAL_MAIN_MENU_STATE = '1_menu'

DEMO_6_MONTH_MENU = '1_1_kmm'
DEMO_12_MONTH_MENU = '1_1_cbf'

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
custom_gm_map_en = {}
custom_gm_map_hi = {}
custom_gm_map_imgs = {}


def setup_state_machines():
    global sm6, sm12
    sm6 = StateMachine(settings.FLOW_6_MONTHS, settings.TRANSLATIONS_6_MONTHS)
    sm12 = StateMachine(settings.FLOW_12_MONTHS,
                        settings.TRANSLATIONS_12_MONTHS)
    _load_custom_gm(settings.GM_FOLDER)


def _load_custom_gm(folder):
    start_dir = os.getcwd()
    os.chdir(folder)
    for _, csv_file in enumerate(glob.glob("*.csv")):
        with open(csv_file, 'r') as f:
            csv_rdr = csv.DictReader(f)
            for row in csv_rdr:
                custom_gm_map_en[row['telegram_id']] = row['english']
                custom_gm_map_hi[row['telegram_id']] = row['hindi']
                custom_gm_map_imgs[row['telegram_id']] = row['image']

    # Reset the working director
    os.chdir(start_dir)


def replace_custom_message(msgs, imgs, context):
    chat_id = str(context.user_data['chat_id'])
    imgs = imgs or []
    if imgs == ['custom_gm']:
        imgs = []
    if 'custom_gm' in msgs:
        imgs.append(os.path.join(settings.GM_FOLDER,
                                 custom_gm_map_imgs[chat_id]))
    if settings.HINDI:
        return [custom_gm_map_hi[chat_id] if m == 'custom_gm' else m for m in msgs], imgs
    return [custom_gm_map_en[chat_id] if m == 'custom_gm' else m for m in msgs], imgs


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
    # Must return:
    # msgs, imgs, state_id, state_name
    menu_state = GLOBAL_MAIN_MENU_STATE
    logger.info(
        f'[{context.user_data["chat_id"]}] - getting menu for user!')
    # Demo users are a special case
    if str(context.user_data['chat_id']) in settings.DEMO_CHAT_IDS:
        menu_state = DEMO_6_MONTH_MENU if context.user_data['track'] == '6' else DEMO_12_MONTH_MENU
        logger.info(
            f'[{context.user_data["chat_id"]}] - DEMO user, fetching special menu!')

    # The "global main menu" is state 1_menu for both of them.
    # Menus have only one message, so we can just take that.
    sm = _get_sm_from_context(context)
    msgs, imgs, _, _, _ = sm.get_msg_and_next_state(
        menu_state, context.user_data['child_gender'])

    msg = msgs[0]

    gm_module = settings.GM_MODULE_6 if int(
        context.user_data['track']) == 6 else settings.GM_MODULE_12
    if menu_state == GLOBAL_MAIN_MENU_STATE and (context.user_data['cohort'] < 2 and context.user_data['cohort'] >= 0):
        # Trim down the menu to content they have seen before in non-demo mode
        msg = '\n'.join(msg.split(
            '\n')[:context.user_data['next_module']])
    elif menu_state == GLOBAL_MAIN_MENU_STATE and context.user_data['cohort'] >= 2 and context.user_data['next_module'] <= gm_module:
        # Keep all content except the GM option
        mparts = msg.split('\n')
        msg = '\n'.join(mparts[:gm_module] + mparts[gm_module+1:])

    return [msg], imgs, sm.get_state_id_from_state_name(menu_state), menu_state

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
    # TODO: Redo this to use the DB-based timeouts. This is cool though!
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
    if img.find('/') < 0:
        return os.path.join('data', 'images', img)
    return img


#################################################
# Telegram bot processing new messages
#################################################
def _log_and_fetch_user_data(update, context):
    logger.info(f'trying to get info for {update.effective_chat.id}')
    fetch_user_data(update.effective_chat.id, context)
    logger.info(f'ending user dict is: {context.user_data}')
    current_state_id, current_state_name = _get_current_state_from_context(
        context)
    logger.info(
        f'fetched the following: {current_state_id}, {current_state_name}')
    _log_msg(update.message.text, 'user', update, state=current_state_name)
    logger.warn(
        f'[{get_chat_id(update, context)}] - intent: {get_intent(update.message.text)} msg received: {update.message.text}')
    return current_state_id, current_state_name


def _save_state_and_process(update, context, msgs, imgs, state_id, state_name):
    current_state_id, _ = _get_current_state_from_context(context)

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


def _escalate_to_nurse(update, context):
    msg = ESCALATE_TEXT
    if settings.HINDI:
        msg = ESCALATE_TEXT_HI
    current_state_id, current_state_name = _get_current_state_from_context(
        context)
    new_escalation = Escalation(
        chat_src_id=update.effective_chat.id,
        first_name=context.user_data['first_name'],
        msg_txt=update.message.text,
        pending=True,
        escalated_time=datetime.utcnow(),
        state_name_when_escalated=current_state_name
    )
    Database().insert(new_escalation)
    nurse_bot._check_nurse_queue(context, new_escalation)
    return [msg], current_state_id, current_state_name


def _handle_echo(update, context):
    intent = get_intent(update.message.text)

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


def _handle_global_reset(update, context):
    msgs, imgs, state_id, state_name = _get_menu_for_user(context)
    _save_user_state(update.effective_chat.id,
                     state_id, state_name)
    msgs = [replace_template(m, context) for m in msgs]
    for msg in msgs:
        send_text_reply(msg, update)
    if imgs:
        for img in imgs:
            send_image_reply(prepend_img_path(img), update)


def _handle_wrong_input(update, context):
    # This is a state transition that doesn't exist (e.g., they typed 6
    # when the menu is only 1-5)
    current_state_id, current_state_name = _get_current_state_from_context(
        context)
    msgs = [WRONG_INPUT]
    imgs = []
    if settings.HINDI:
        msgs = [WRONG_INPUT_HI]
    # Repeat our message.
    sm = _get_sm_from_context(context)
    if current_state_name == GLOBAL_MAIN_MENU_STATE:
        new_msgs, _, _, _ = _get_menu_for_user(context)
        msgs = msgs + new_msgs
    else:
        # Largely unncessary, but maybe there's some version where this would happen
        repeat_msgs, imgs, _, _, _ = sm.get_msg_and_next_state(
            current_state_name, context.user_data['child_gender'])
        repeat_msgs, imgs = replace_custom_message(repeat_msgs, imgs, context)
        msgs = msgs + repeat_msgs
    return _save_state_and_process(update, context, msgs, imgs, current_state_id, current_state_name)


def _handle_global_menu_input(update, context):
    intent = get_intent(update.message.text)
    max_module = settings.MAX_MODULE_6 if int(
        context.user_data['track']) == 6 else settings.MAX_MODULE_12
    gm_module = settings.GM_MODULE_6 if int(
        context.user_data['track']) == 6 else settings.GM_MODULE_12
    if intent < Intent.ONE or intent > Intent.TEN:
        # Input was way off, so escalate up to the nurse
        msgs, state_id, state_name = _escalate_to_nurse(update, context)
        return _save_state_and_process(update, context, msgs, [], state_id, state_name)
    elif intent >= context.user_data['next_module'] and context.user_data['cohort'] < 2:
        # They gave a number input, but it was out of bounds, so just re-prompt them
        return _handle_wrong_input(update, context)
    elif context.user_data['cohort'] >= 2 and (intent > max_module or (
            gm_module >= context.user_data['next_module'] and intent == gm_module)):
        # They gave a number input, but it was out of bounds, so just re-prompt them
        return _handle_wrong_input(update, context)

    # Ok, we have valid input from our current state, so we can process it
    return _handle_valid_input(update, context)


def _handle_valid_input(update, context):
    current_state_id, _ = _get_current_state_from_context(
        context)
    if current_state_id is None or current_state_id == '':
        return _handle_global_reset(update, context)

    # Get the correct state machine
    sm = _get_sm_from_context(context)
    intent = get_intent(update.message.text)

    try:
        msgs, imgs, state_id, state_name, terminal = sm.get_msg_and_next_state(
            current_state_id, context.user_data['child_gender'], intent)
    except ValueError:
        # Ok, something went wrong with the input and a transition.
        # We already know it is a numeric input as a precodition, so we can
        # ask for the input again
        return _handle_wrong_input(update, context)

    # Ok, valid input and valid transition!
    msgs, imgs = replace_custom_message(msgs, imgs, context)
    _save_state_and_process(update, context, msgs, imgs, state_id, state_name)

    # Last bit, if it's a leaf node, send them back to the main menu
    # UNLESS we have a nurse state
    if terminal and not sm.is_nurse_state(state_name):
        return _handle_global_reset(update, context)


def process_user_input(update, context):
    """Handle a user message."""
    # Log and fetch user data
    _, current_state_name = _log_and_fetch_user_data(
        update, context)

    # Special case: handle the echo state
    if current_state_name == 'echo':
        logger.info(
            f'[{get_chat_id(update, context)}] - Calling echo')
        return _handle_echo(update, context)

    # Reset timers
    remove_old_timer_add_new(context)

    # Handle global reset
    intent = get_intent(update.message.text)
    # if intent == Intent.GREET or intent == Intent.RESTART:
    if intent == Intent.GREET:
        logger.info(
            f'[{get_chat_id(update, context)}] - Calling global reset')
        return _handle_global_reset(update, context)

    # handle global main menu inputs
    if current_state_name == GLOBAL_MAIN_MENU_STATE:
        logger.info(
            f'[{get_chat_id(update, context)}] - Calling global menu input')
        return _handle_global_menu_input(update, context)

    # Before we move on, check if we are currently in a state to speak to the nurse
    sm = _get_sm_from_context(context)
    if sm.is_nurse_state(current_state_name):
        # The message should go direct to the nurse
        msgs, state_id, state_name = _escalate_to_nurse(update, context)
        return _save_state_and_process(update, context, msgs, [], state_id, state_name)

    # Handle unknown
    # TODO: In the future we will change this section to allow non-numeric
    # input (e.g., yes and no as appropriate )
    if intent < Intent.ONE or intent > Intent.TEN:
        # Non-numeric input at this stage, so escalate up to the nurse.
        msgs, state_id, state_name = _escalate_to_nurse(update, context)
        return _save_state_and_process(update, context, msgs, [], state_id, state_name)

    # Handle valid input (standard case)
    return _handle_valid_input(update, context)
    # Handle quick state transitions for quiz??
