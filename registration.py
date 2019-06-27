from datetime import datetime

from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, RegexHandler,
                          ConversationHandler)
from db import User, Database
from send import send_text_reply, _log_msg
from customnlu import interpreter, get_intent, Intent
from simple_settings import settings

# Define the states
CONFIRM_NAME, ASK_NAME, ASK_CHILD_NAME, ASK_CHILD_GENDER, ASK_CHILD_BIRTHDAY, PHONE_NUMBER, AWW_LIST, AWW_NUMBER, AWC_CODE = range(
    9)


def cancel(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_cancel')
    send_text_reply('cancel called, ending registration flow',
                    update, state='registration_cancel')
    return ConversationHandler.END


def start(update, context):
    # TODO: Update this once we are ready to launch?
    if settings.HINDI:
        send_text_reply(
            'नमस्ते और आपका स्वागत है। मेरा नाम पोशन दीदी है और मैं इस समय विकसित हो रही हूँ।', update, state='registration_1')
        send_text_reply(
            f'क्या मैं आपको {update.message.from_user.first_name} कह सकती हूं?', update, state='registration_1')
    else:
        send_text_reply(
            'Hello and welcome. My name is Poshan Didi and I am currently under development.', update, state='registration_1')
        send_text_reply(
            f'Can I call you {update.message.from_user.first_name}?', update, state='registration_1')
    return CONFIRM_NAME


def _save_name(update, context, name):
    # Don't save because we will have saved input before this is called.
    # _log_msg(update.message.text, 'user', update, state='registration')
    context.user_data['preferred_name'] = name
    if settings.HINDI:
        send_text_reply(
            f'ठीक है, धन्यवाद {name}। कृपया मुझे बताएं कि मुझे आपके बच्चे को क्या कहना चाहिए (उनका दिया गया पहला नाम ही काफी रहेगा)।', update, state='registration_2')
    else:
        send_text_reply(
            f'Ok, thank you {name}. Please tell me what I should call your child (just a first name is fine).', update, state='registration_2')
    return ASK_CHILD_NAME


def confirm_name(update, context):
    _log_msg(update.message.text, 'user', update, state='registration')
    intent = get_intent(update.message.text)
    if intent == Intent.YES:
        return _save_name(update, context, update.message.from_user.first_name)
    elif intent == Intent.NO:
        if settings.HINDI:
            send_text_reply(
                'ठीक है, कोई बात नहीं। आप मुझसे खुद को क्या बुलवाना पसंद करेंगी (बस एक पहला नाम ठीक है)?', update, state='registration_1b')
        else:
            send_text_reply(
                'Ok, no problem. What would you like me to call you (just a first name is fine)?', update, state='registration_1b')
        return ASK_NAME

    if settings.HINDI:
        send_text_reply(
            f"मुझे वह सही से समझ नहीं आया। कृपया 'हां' या 'नहीं' के साथ जवाब दें। क्या मैं आपको {update.message.from_user.first_name} कह कर आपसे बात कर सकती हूँ?", update, state='registration_1x')
    else:
        send_text_reply(
            f"I didn't quite get that. Please respond with 'yes' or 'no'. Can I call you {update.message.from_user.first_name}?", update, state='registration_1x')
    return CONFIRM_NAME


def ask_name(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_2b')
    return _save_name(update, context, update.message.text)


def ask_child_name(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_3')
    name = context.user_data['preferred_name']
    context.user_data['child_name'] = update.message.text

    if settings.HINDI:
        send_text_reply(
            f'ठीक है, धन्यवाद {name} - मैं आपके बच्चे को {update.message.text} के नाम से बुलाऊंगी। बस हो गया- कुछ और प्रश्न रह रहे हैं।\n\n'
            f'आपके बच्चे का लिंग क्या है?\n'
            f'1) लड़की\n'
            f'2) लड़का', update, state='registration_3')
    else:
        send_text_reply(
            f'Ok, thank you {name}--I will refer to your child as {update.message.text}.\n\nAlmost done--just a few more questions. '
            f'What is the gender of your child?\n1) Girl\n2) Boy', update, state='registration_3')
    return ASK_CHILD_GENDER


def save_child_gender(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_3.5')
    intent = get_intent(update.message.text)
    if intent == Intent.ONE:
        context.user_data['child_gender'] = 'F'
    elif intent == Intent.TWO:
        context.user_data['child_gender'] = 'M'
    else:
        if settings.HINDI:
            send_text_reply(
                f"मुझे वह सही से समझ नहीं आया। कृपया '1' या '2' के साथ जवाब दें। आपके बच्चे का लिंग क्या है?\n1) लड़की\n2) लड़का", update, state='registration_3.5x')
        else:
            send_text_reply(
                f"I didn't quite get that. Please respond with '1' or '2'. What is the gender of your child?\n1) Girl\n2) Boy?", update, state='registration_3.5x')
        return ASK_CHILD_GENDER

    if settings.HINDI:
        send_text_reply(
            f'{context.user_data["child_name"]} की जन्म की तारिख कब की है? कृपया उस संख्या को इस प्रारूप में लिखें: YYYY-MM-DD (साल-महीना-महीने का दिन)', update, state='registration_3.5')
    else:
        send_text_reply(
            f'What is the birthday for {context.user_data["child_name"]}? Please enter in this format: YYYY-MM-DD', update, state='registration_3.5')
    return ASK_CHILD_BIRTHDAY


def wrong_child_birthday(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_4b')
    if settings.HINDI:
        send_text_reply(
            f"{context.user_data['child_name']} की जन्म की तारिख कब की है? कृपया उस संख्या को इस प्रारूप में लिखें: YYYY-MM-DD (साल-महीना-महीने का दिन)", update, state='registration_4b')
    else:
        send_text_reply(
            f"What is the birthday for {context.user_data['child_name']}? Please enter in this format: YYYY-MM-DD", update, state='registration_4b')
    return ASK_CHILD_BIRTHDAY


def ask_child_birthday(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_4')

    # Determine the track based on 5 months
    if (datetime.utcnow() - datetime.strptime(update.message.text, '%Y-%m-%d')).days >= 365:
        return wrong_child_birthday(update, context)
    elif (datetime.utcnow() - datetime.strptime(update.message.text, '%Y-%m-%d')).days >= 150:
        context.user_data['track'] = 12
        if settings.HINDI:
            send_text_reply('ठीक है, 6-12 महीने।', update,
                            state='registration_4')
        else:
            send_text_reply('Ok, 6-12 months.', update, state='registration_4')
    else:
        context.user_data['track'] = 6
        if settings.HINDI:
            send_text_reply('ठीक है, 0-6 महीने।', update,
                            state='registration_4')
        else:
            send_text_reply('Ok, 0-6 months.', update, state='registration_4')

    # Save after the error checking and track determination above
    context.user_data['child_birthday'] = update.message.text

    if settings.HINDI:
        send_text_reply(
            f'समझ गयी। आपका फोन नंबर क्या है? कृपया उसे निम्न प्रारूप में दर्ज करें: + 91dddddddddd, जहां प्रत्येक d एक संख्या है।', update, state='registration_4')
    else:
        send_text_reply(
            f'Got it. What is your phone number? Please enter it in the following format: +91dddddddddd, where each d is a number', update, state='registration_4')
    return PHONE_NUMBER


def wrong_phone_number(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_5b')
    if settings.HINDI:
        send_text_reply(
            f'आपका फोन नंबर क्या है? कृपया उसे निम्न प्रारूप में दर्ज करें: + 91dddddddddd, जहां प्रत्येक d एक संख्या है।', update, state='registration_5b')
    else:
        send_text_reply(
            f'What is your phone number? Please enter it in the following format: +91dddddddddd, where each d is a number', update, state='registration_5b')
    return PHONE_NUMBER


def phone_number(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_5')
    # Our regex lets the users put in white space, so strip it all out
    # (this doesnt actually matter, but is nice)
    context.user_data['phone_number'] = update.message.text.replace(' ', '')
    if settings.HINDI:
        send_text_reply(
            f'बहुत अच्छे! बस कुछ सवाल। आपकी आंगनवाड़ी कार्यकर्ता का क्या नाम है?', update, state='registration_5')
    else:
        send_text_reply(
            f'Ok, last few questions. What is the name of the AWW here?', update, state='registration_5')
    return AWW_LIST


def ask_aww_number(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_6')
    context.user_data['aww'] = update.message.text
    if settings.HINDI:
        send_text_reply(
            f'धन्यवाद! {update.message.text} के लिए फ़ोन नंबर क्या है? कृपया इसे निम्न प्रारूप में दर्ज करें: + 91dddddddddd, जहां प्रत्येक d एक संख्या है', update, state='registration_6')
    else:
        send_text_reply(
            f'Great! What is the phone number for {update.message.text}? Please enter it in the following format: +91dddddddddd, where each d is a number', update, state='registration_6')
    return AWW_NUMBER


def wrong_aww_number(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_6b')
    if settings.HINDI:
        send_text_reply(
            f'{context.user_data["aww"]} के लिए फ़ोन नंबर क्या है? कृपया इसे निम्न प्रारूप में दर्ज करें: + 91dddddddddd, जहां प्रत्येक d एक संख्या है', update, state='registration_6')
    else:
        send_text_reply(
            f'What is the phone number for {context.user_data["aww"]}? Please enter it in the following format: +91dddddddddd, where each d is a number', update, state='registration_6')
    return AWW_NUMBER


def ask_awc_code(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_7')
    # Our regex lets the users put in white space, so strip it all out
    # (this doesnt actually matter, but is nice)
    context.user_data['aww_number'] = update.message.text.replace(' ', '')
    if settings.HINDI:
        send_text_reply(
            f'धन्यवाद! अंतिम प्रश्न: आपके आंगनवाड़ी सेंटर का कोड क्या है?', update, state='registration_7')
    else:
        send_text_reply(
            f'Thanks! Last question: what is the AWC code?', update, state='registration_7')
    return AWC_CODE


def thanks(update, context):
    _log_msg(update.message.text, 'user', update, state='registration_final')
    context.user_data['awc_code'] = update.message.text
    # SAVE THE USER
    new_user = User(
        chat_id=update.effective_chat.id,
        first_name=context.user_data['preferred_name'],
        last_name=update.message.from_user.last_name,
        track=context.user_data['track'],
        phone_number=context.user_data['phone_number'],
        child_name=context.user_data['child_name'],
        child_gender=context.user_data['child_gender'],
        child_birthday=datetime.strptime(
            context.user_data['child_birthday'], '%Y-%m-%d'),
        current_state='echo',
        current_state_name='echo',
        aww=context.user_data['aww'],
        aww_number=context.user_data['aww_number'],
        awc_code=context.user_data['awc_code']
    )
    Database().insert(new_user)
    if settings.HINDI:
        send_text_reply(
            "धन्यवाद! अब आप पंजीकृत हैं।", update, state='registration_final')
        send_text_reply(
            "कृपया अपने पहले संदेश की प्रतीक्षा करें, जो अगले 7 दिनों के भीतर मेरे द्वारा आना चाहिए। आप मेरे द्वारा भेजे गए किसी भी सन्देश को फिर से पा सकते हैं, बस किसी भी समय हेल्लो टाइप करके!", update, state='registration_final')
        send_text_reply(
            "यदि आप मेरे द्वारा पहला संदेश भेजने से पहले थोड़ा अभ्यास करना चाहते हैं, तो कृपया 1 से 9 के बीच कोई भी संख्या दर्ज करें और मैं आपको बताउंगी कि मैंने क्या समझा।", update, state='registration_final')
    else:
        send_text_reply(
            "Thank you! You're registered. Please wait for your first message, that should come within the next 7 days. You can access all content I have sent you after that just by typing hello at any time! If you want to practice before I sent you the first message, please enter a number between 1 to 9 and I will tell you what I understood. ", update, state='registration_final')
    return ConversationHandler.END


registration_conversation = ConversationHandler(
    entry_points=[CommandHandler('start', start)],

    states={
        CONFIRM_NAME: [MessageHandler(Filters.text, confirm_name)],

        ASK_NAME: [MessageHandler(Filters.text, ask_name)],

        ASK_CHILD_NAME: [MessageHandler(Filters.text, ask_child_name)],

        ASK_CHILD_GENDER: [MessageHandler(Filters.text, save_child_gender)],

        ASK_CHILD_BIRTHDAY: [MessageHandler(Filters.regex('^201[8,9]-[0,1][0-9]-[0,1,2,3][0-9]$'), ask_child_birthday),
                             MessageHandler(~Filters.regex('^201[8,9]-[0,1][0-9]-[0,1,2,3][0-9]$'), wrong_child_birthday)],

        PHONE_NUMBER: [MessageHandler(Filters.regex('^\+9\s*1\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*$'), phone_number),
                       MessageHandler(~Filters.regex('^\+9\s*1\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*$'), wrong_phone_number)],

        AWW_LIST: [MessageHandler(Filters.text, ask_aww_number)],

        AWW_NUMBER: [MessageHandler(Filters.regex('^\+9\s*1\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*$'), ask_awc_code),
                     MessageHandler(~Filters.regex('^\+9\s*1\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*$'), wrong_aww_number)],

        AWC_CODE: [MessageHandler(Filters.text, thanks)],
    },

    fallbacks=[CommandHandler('cancel', cancel)]
)
