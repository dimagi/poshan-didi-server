from datetime import datetime
import logging
import re

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
# Send module messages!
#################################################
WA_TEMPLATE_6 = "नमस्कार {{1}}! मैं पोषण दीदी हूँ (मैं मध्य प्रदेश महिला एवं बाल विकास संचालनालय के साथ जुड़ी हुई हूँ)। क्यूंकि आपका बच्चा {{2}} महीने का हो गया है, ये महत्वपूर्ण है की आप उसे विशेष रूप से केवल स्तनपान कराएं।"
WA_TEMPLATE_12 = "नमस्कार {{1}}! मैं पोषण दीदी हूँ (मैं मध्य प्रदेश महिला एवं बाल विकास संचालनालय के साथ जुड़ी हुई हूँ)। क्यूंकि आपका बच्चा {{2}} महीने का हो गया है, ये महत्वपूर्ण है की आप उसे क्या ऊपरी आहार देंगी उसके बारे में सोचना शुरू करें।"

WA_TEMPLATE_B = "नमस्कार {{1}}! मैं पोषण दीदी हूँ (मैं मध्य प्रदेश महिला एवं बाल विकास संचालनालय के साथ जुड़ी हुई हूँ)। क्यूंकि आपका बच्चा {{2}} सप्ताह का हो गया है, तो यह महत्वपूर्ण है कि आप {{3}} की पोषण संबंधी बढ़ती जरूरतों पर विचार करें।याद रखें कि आप अतिरिक्त पोषण जानकारी पाने के लिए किसी भी समय 'हैलो' टाइप कर सकते हैं।"
def _send_next_module_and_log(update, context, user):
    # Find state associated with the next_module
    sm = beneficiary_bot.get_sm_from_track(user.track)
    next_state_name = sm.get_submodule_state_name(f'1_{user.next_module}_')
    next_state_id = sm.get_state_id_from_state_name(next_state_name)

    # Get the content
    msgs, imgs, _, _, _ = sm.get_msg_and_next_state(
        next_state_name, user.child_gender)
    beneficiary_bot.fetch_user_data(user.chat_id, context)
    msgs, imgs = beneficiary_bot.replace_custom_message(msgs, imgs, context)

    if str(user.chat_id).startswith('whatsapp:'):
        # Manually adjust messages to the 
        if int(user.next_module) % 2 == 0:
            msg_template = WA_TEMPLATE_B
            weeks_old = (datetime.now() - user.child_birthday).days // 7 
            msg_template = msg_template.replace('{{1}}', user.first_name)
            msg_template = msg_template.replace('{{2}}', str(int(weeks_old)))
            msg_template = msg_template.replace('{{3}}', user.child_name)
        else:
            msg_template = WA_TEMPLATE_6 if int(user.track) == 6 else WA_TEMPLATE_12
            msg_template = msg_template.replace('{{1}}', user.first_name)
            # Calculate months based on the WHO standard. This may be off by a couple days, 
            # but that's fine for our purposes. 
            months_old = (datetime.now() - user.child_birthday).days // 30.625
            msg_template = msg_template.replace('{{2}}', str(int(months_old)))
        msgs = [msg_template]
        imgs = []

    # Send the content
    for msg_txt in msgs:
        # Log the message from system-new-module to the user
        _log_msg(beneficiary_bot.replace_template(msg_txt, context), 'system-new-module', update,
                 state=Database().get_state_name_from_chat_id(user.chat_id),
                 chat_id=str(user.chat_id))
        # And send it
        context.bot.send_message(
            user.chat_id, beneficiary_bot.replace_template(msg_txt, context))

    for img in imgs:
        # Log the image from system-new-module to the user
        _log_msg(img, 'system-new-module', update,
                 state=Database().get_state_name_from_chat_id(user.chat_id),
                 chat_id=str(user.chat_id))
        # And send it
        f = open(beneficiary_bot.prepend_img_path(img), 'rb')
        context.bot.send_photo(
            user.chat_id, f)
        f.close()

    user.current_state = next_state_id
    user.current_state_name = next_state_name
    return user


def send_next_module(update, context, cohort):
    # Find all the users whose:
    # - next_module is less than max
    # - not a test user
    # - Registration was before cutoff
    users = Database().session.query(User).filter(
        (User.test_user == False) &
        (User.cohort == cohort) &
        (((User.track == '6') & (User.next_module <= settings.MAX_MODULE_6)) |
            ((User.track == '12') & (User.next_module <= settings.MAX_MODULE_12)))
    )

    for user in users:
        # Send out messages to user
        beneficiary_bot.fetch_user_data(user.chat_id, context)
        user = _send_next_module_and_log(update, context, user)

        # Increment next_module
        user.next_module = user.next_module + 1

        # Set 'started' and 'first_msg_date' if needed
        if not user.started:
            user.started = True
            user.first_msg_date = datetime.utcnow()

    # Save back to DB
    Database().commit()
    return users.count()


def send_next_modules(update, context):
    logger.warning('Send next modules called in GOD mode!')
    _log_msg(update.message.text, 'GOD', update)

    # Check syntax
    try:
        cmd_parts = update.message.text.split()
        if len(cmd_parts) != 2:
            logger.warning('Send next modules: wrong number of args')
            raise Exception()
        cohort = cmd_parts[1]
    except:
        send_text_reply(
            'Usage details for send next modules: /send_next_modules <cohort>, where the cohort is the group to increment', update)
        return

    user_count = send_next_module(
        update, context, cohort)

    return send_text_reply(
        f'Successfully changed the state for {user_count} users!', update)


#################################################
# Nurse queue
#################################################
def _check_nurse_queue(context, escalation=None):
    first_pending = Database().get_nurse_queue_first_pending()
    try:
        relevant_messages = Database().session.query(
            Escalation
        ).filter_by(pending=True, chat_src_id=first_pending.chat_src_id)
    except AttributeError:
        # No pending messages
        return

    # If escalation exists, then only send if the escalation is relevant
    if escalation and first_pending.chat_src_id != escalation.chat_src_id:
        return

    for msg in relevant_messages:
        _log_msg(msg.msg_txt, 'system-unsent', None, msg.state_name_when_escalated,
                 chat_id=settings.NURSE_CHAT_ID)
        #  TODO: does the line below make any sense??
        msg.replied_time = datetime.utcnow()

    nl = '\n'
    msg = (f"The following message(s) are from "
           f"'{first_pending.first_name}' ({first_pending.chat_src_id}). "
           f"Your reply will be forwarded automatically.\n\n"
           f"{nl.join([m.msg_txt for m in relevant_messages])}")
    context.bot.send_message(
        settings.NURSE_CHAT_ID,
        msg
    )
    # Database().commit()


def skip(update,context):
    if not _check_pending(update,context,"No pending messages to skip!"):
        return

    escalation = Database().get_nurse_queue_first_pending()
    Database().nurse_queue_mark_answered(escalation.chat_src_id)
    send_text_reply(
        f"Ok. Successfully skipped one pending message from {escalation.first_name} ({escalation.chat_src_id}).", update)
    _check_nurse_queue(context)

def _check_pending(update, context, none_pending_msg):
    if not Database().nurse_queue_pending():
        send_text_reply(none_pending_msg, update)
        logger.info(
            f'[{beneficiary_bot.get_chat_id(update, context)}] - no pending nurse messages....')
        return False
    return True


def _send_message_to_queue(update, context, msgs_txt, imgs=[]):
    """Send msg_text to the user at the top of the nurse queue
    This does not update the queue (in case we want to send multiple messages.
    This will, however, log everything correctly"""
    escalation = Database().get_nurse_queue_first_pending()
    beneficiary_bot.fetch_user_data(escalation.chat_src_id, context)

    for msg_txt in msgs_txt:
        # Log the message from nurse to the user
        _log_msg(beneficiary_bot.replace_template(msg_txt, context), 'nurse', update,
                 state=Database().get_state_name_from_chat_id(escalation.chat_src_id),
                 chat_id=str(escalation.chat_src_id))
        # And send it
        context.bot.send_message(
            escalation.chat_src_id, beneficiary_bot.replace_template(msg_txt, context))

    for img in imgs:
        # Log the image from nurse to the user
        _log_msg(img, 'nurse', update,
                 state=Database().get_state_name_from_chat_id(escalation.chat_src_id),
                 chat_id=str(escalation.chat_src_id))
        # And send it
        f = open(beneficiary_bot.prepend_img_path(img), 'rb')
        context.bot.send_photo(
            escalation.chat_src_id, f)
        f.close()

def _send_message_to_chat_id(update, context, chat_id, msgs_txt):
    """Send msg_text to a specific chat_id from GOD mode."""
    beneficiary_bot.fetch_user_data(chat_id, context)

    for msg_txt in msgs_txt:
        # Log the message from nurse to the user
        _log_msg(beneficiary_bot.replace_template(msg_txt, context), 'GOD', update,
                 state=Database().get_state_name_from_chat_id(chat_id),
                 chat_id=str(chat_id))
        # And send it
        context.bot.send_message(
            chat_id, beneficiary_bot.replace_template(msg_txt, context))


def _send_images_to_chat_id(update, context, chat_id, imgs):
    """Send msg_text to a specific chat_id from GOD mode."""
    beneficiary_bot.fetch_user_data(chat_id, context)

    for img in imgs:
        # Log the message from nurse to the user
        _log_msg(img, 'GOD', update,
                 state=Database().get_state_name_from_chat_id(chat_id),
                 chat_id=str(chat_id))
        # And send it
        f = open(beneficiary_bot.prepend_img_path(img), 'rb')
        context.bot.send_photo(
            chat_id, f)
        f.close()


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
    msgs, imgs, _, _, _ = sm.get_msg_and_next_state(
        new_state, our_user.child_gender)
    beneficiary_bot.fetch_user_data(chat_id, context)
    msgs, imgs = beneficiary_bot.replace_custom_message(msgs, imgs, context)
    _send_message_to_queue(
        update, context, msgs, imgs
    )

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
    msgs, imgs, _, _, _ = sm.get_msg_and_next_state(
        new_state, our_user.child_gender)
    beneficiary_bot.fetch_user_data(chat_id, context)
    msgs, imgs = beneficiary_bot.replace_custom_message(msgs, imgs, context)
    _send_message_to_chat_id(
        update, context, chat_id,
        msgs)
    _send_images_to_chat_id(
        update, context, chat_id,
        imgs)

    # Tell the nurse and check the queue
    send_text_reply(
        f"Ok. State successfully set to {new_state} and message sent to the user.", update)
    _check_nurse_queue(context)

def set_cohort_super_state(update, context):
    # Save the mssage the nurse sent in
    logger.warning('Set SUPER cohort-state called in GOD mode!')
    _log_msg(update.message.text, 'GOD', update)

    # Check syntax of the command
    try:
        cmd_parts = update.message.text.split()
        if len(cmd_parts) != 3:
            raise Exception()
        cohort = cmd_parts[1]
        new_state = cmd_parts[2]
    except:
        send_text_reply(
            "Usage details for GOD mode: /cohortstate <cohort_number> <new_state_name>", update)
        return

    # Find all the users whose:
    # - not a test user
    # - in the correct cohort
    users = Database().session.query(User).filter(
        ((User.test_user == False) &
        (User.cohort == cohort))
    )

    for user in users:
        # set the state for the user!
        sm = beneficiary_bot.get_sm_from_track(user.track)
        try:
            state_id = sm.get_state_id_from_state_name(new_state)
        except ValueError:
            send_text_reply(
                f"for GOD mode: /cohortstate <cohort_number> <new_state_name>\n'{new_state}' not recognized as a valid state.", update)
            return False
        user.current_state = state_id
        user.current_state_name = new_state

        msgs, imgs, _, _, _ = sm.get_msg_and_next_state(
            new_state, user.child_gender)
        beneficiary_bot.fetch_user_data(user.chat_id, context)
        msgs, imgs = beneficiary_bot.replace_custom_message(msgs, imgs, context)
        _send_message_to_chat_id(
            update, context, user.chat_id,
            msgs)
        _send_images_to_chat_id(
            update, context, user.chat_id,
            imgs)

    # Save back to DB
    Database().commit()
    # Tell the nurse and check the queue
    send_text_reply(
        f"Ok. State successfully set to {new_state} and message sent to {users.count()} users in cohort {cohort}.", update)


date_re = re.compile('[0-3]\d-[0-1]\d-[1-2]\d\d\d')
date_y_first_re = re.compile('[1-2]\d\d\d-[0-1]\d-[0-3]\d')


def send_vhnd_reminder(update, context):
    logger.warning('Send VHND reminder called in GOD mode!')
    _log_msg(update.message.text, 'GOD', update)

    # Check syntax
    try:
        cmd_parts = update.message.text.split()
        if len(cmd_parts) != 3:
            logger.warning('Send VHND reminder: wrong number of args')
            raise Exception()
        awc_id = cmd_parts[1]
        date = cmd_parts[2]
        if len(awc_id) != 11 or date_re.match(date) is None:
            logger.warning(
                f'Send VHND reminder: PROBLEM with arguments AWC chars:{len(awc_id)}')
            raise Exception()
    except:
        send_text_reply(
            'Usage details for VHND: /vhnd <awc_id> <DD-MM-YYYY>', update)
        return

    users = Database().session.query(User).filter_by(awc_code=awc_id)
    logger.warning(f'Found {users.count()} users for AWC code {awc_id}')
    for user in users:
        if settings.HINDI:
            msg = f'नमस्ते [mother name]! आपके क्षेत्र में टीकाकरण दिवस {date} को हो रहा है । अपने बच्चे [child name] के साथ अपने आंगनवाड़ी केंद्र जाना ना भूलें!'
        else:
            msg = f'Hello [mother name]! The VHSND in your area is happening on {date}. Make sure to go to your AWC with [child name]!'

        logger.info(f'sending {msg} to {user.chat_id}')
        _send_message_to_chat_id(
            update, context, user.chat_id, [msg]
        )
    if users.count() > 0:
        send_text_reply(
            f"Ok. Successfully sent VHND reminders to {users.count()} users.", update)
    else:
        send_text_reply(
            f"Unable to find any users with AWC code {awc_id}", update)


def send_global_msg(update,context):
    pre_sign_off="मेरे साथ इस गतिविधि में भाग लेने और बात करने के लिए धन्यवाद! पोशन दीदी के साथ बात-चीत करने का परीक्षण अक्टूबर 15, 2019 को समाप्त हो जाएगा जिसके बाद मैं उपलब्ध नहीं रहूंगी। यदि आपके पास मेरे लिए कोई और प्रश्न हैं, तो कृपया अंतिम तिथि से पहले मुझे संदेश भेजें।"
    users = Database().session.query(User)

    for user in users:
        if user.chat_id.startswith('whatsapp') or user.cohort < 0 or user.cohort > 20:
            continue
        logger.info(f'sending pre sign off to {user.chat_id}')
        try:
            _send_message_to_chat_id(
                update,context,user.chat_id,[pre_sign_off]
            )
        except:
            logger.warning(f'Error sending pre sign off to {user.chat_id}')
    
    if users.count() > 0:
        send_text_reply(
            f"Ok. Successfully sent pre sign off to to {users.count()} users.", update)
    else:
        send_text_reply(
            f"Unable to find any users to send pre sign off message", update)


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
