from datetime import date, datetime, timedelta
import time

import json
import os
from flask import Flask, render_template, request, make_response, current_app
from functools import update_wrapper
import beneficiary_bot
import nurse_bot
from simple_settings import settings

from telegram.ext import JobQueue

# TODO move this with the stub
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from db import User, Message, Database

app = Flask(__name__)
db = Database()
beneficiary_bot.setup_state_machines()

# TODO: Move to a stub somehwere
class FakeContext(object):
    def __init__(self):
        self.user_data = {}
        self.bot = FakeBot()
        self.job_queue = JobQueue(self.bot)

class FakeBot(object):
    def send_message(self, chat_id, text):
        msg = FakeMessage(text,chat_id)
        msg.reply_text(text)
    def send_photo(self, chat_id, f):
        msg = FakeMessage(f.name,chat_id)
        msg.reply_photo(f)

class FakeChat(object):
    def __init__(self, id):
        self.id = id
class FakeMessage(object):
    def __init__(self, text,chat_id):
        self.text = text
        self.chat_id = chat_id
    
    def reply_text(self,txt, ** kwargs):
        client = Client(settings.WHATSAPP_ACCOUNT, settings.WHATSAPP_AUTH)
        if self.chat_id == settings.NURSE_CHAT_ID:
            self.chat_id = settings.NURSE_CHAT_ID_WHATSAPP
        client.messages.create(
            body=txt,
            from_=settings.WHATSAPP_FROM,
            to=self.chat_id
        )        
        print(f"Reply on WhatsApp sent! {txt}")

    def reply_photo(self,f, ** kwargs):
        # TODO: fix growth monitoring as well!
        filename = f.name
        filename = filename[filename.rfind('/')+1:]

        url = f'https://poshan-didi.commcarehq.org/public/{filename}'
        client = Client(settings.WHATSAPP_ACCOUNT, settings.WHATSAPP_AUTH)
        if self.chat_id == settings.NURSE_CHAT_ID:
            self.chat_id = settings.NURSE_CHAT_ID_WHATSAPP
        client.messages.create(
            body='',
            from_=settings.WHATSAPP_FROM,
            to=self.chat_id,
            media_url=url
        )
        # HACK!
        # Sleep for 5 seconds so the picture can send. 
        # For the record, I feel bad about this.
        time.sleep(5)
        print("Fake send an image reply to WhatsApp!")

class FakeUpdate(object):
    def __init__(self, chat_id, msg):
        self.effective_chat = FakeChat(chat_id)
        self.message = FakeMessage(msg,chat_id)


# Thanks
# https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))

# Thanks
# https://codybonney.com/allow-cross-origin-resource-sharing-cors-using-flask/
# TODO: There is probably a better way to handle this, but just make sure
# it's not being used for production


def crossdomain(debug=False, origin=None, methods=None, headers=None, max_age=21600, attach_to_all=True, automatic_options=True):
    if methods is not None:
        methods = ', '.join(sorted(x.upper() for x in methods))
    if headers is not None and not isinstance(headers, str):
        headers = ', '.join(x.upper() for x in headers)
    if not isinstance(origin, str):
        origin = ', '.join(origin)
    if isinstance(max_age, timedelta):
        max_age = max_age.total_seconds()

    def get_methods():
        if methods is not None:
            return methods

        options_resp = current_app.make_default_options_response()
        return options_resp.headers['allow']

    def decorator(f):
        if debug == False:
            return f

        def wrapped_function(*args, **kwargs):
            if automatic_options and request.method == 'OPTIONS':
                resp = current_app.make_default_options_response()
            else:
                resp = make_response(f(*args, **kwargs))
            if not attach_to_all and request.method != 'OPTIONS':
                return resp

            h = resp.headers

            h['Access-Control-Allow-Origin'] = origin
            h['Access-Control-Allow-Methods'] = get_methods()
            h['Access-Control-Max-Age'] = str(max_age)
            if headers is not None:
                h['Access-Control-Allow-Headers'] = headers
            return resp

        f.provide_automatic_options = False
        return update_wrapper(wrapped_function, f)
    return decorator


@app.route('/')
def homepage():
    return render_template('index.html')


@app.route('/callback/v1/twilio', methods = ['POST'])
def twilio_msg():
    msg_id = request.values.get('SmsMessageSid',None)
    chat_id = request.values.get('From',None)
    msg = request.values.get('Body',None)

    # empty context because we're not using telegram
    context = FakeContext()
    update = FakeUpdate(chat_id, msg)
    beneficiary_bot.fetch_user_data(chat_id,context)
    if context.user_data['child_name'] == 'NONE':
        # If this user does not exist, create a user in the DB and set to echo state
        # HACK: to calculate the cohort
        d1 = datetime(2019, 6, 26)
        d2 = datetime.utcnow()
        monday1 = (d1 - timedelta(days=d1.weekday()))
        monday2 = (d2 - timedelta(days=d2.weekday()))
        cohort = (monday2 - monday1).days // 7
        new_user = User(
            chat_id=chat_id, 
            cohort=cohort,        
            current_state='echo',
            current_state_name='echo',
            registration_date=datetime.utcnow(),
            test_user=False
        )
        db.insert(new_user)
        beneficiary_bot.fetch_user_data(chat_id,context)

    # if chat_id == settings.NURSE_CHAT_ID_WHATSAPP:
    #     print(f"calling nurse input for {msg}")
    #     # Process nurse commands and such
    #     if msg.startswith('/noreply'):
    #         nurse_bot.skip(update,context)
    #     elif msg.startswith('/state'):
    #         nurse_bot.set_state(update,context)
    #     else:
    #         nurse_bot.process_nurse_input(update,context)
    # elif chat_id == settings.GOD_MODE_WHATSAPP:
    #     # Handle the GOD mode 
    #     print(f"calling GOD-mode input for {msg}")
    #     if msg.startswith('/state'):
    #         nurse_bot.set_super_state(update,context)
    #     elif msg.startswith('/cohortstate'):
    #         nurse_bot.set_cohort_super_state(update,context)
    #     elif msg.startswith('/send_next_modules'):
    #         nurse_bot.send_next_modules(update,context)
    # else:
    #     # Process normal user commands
    #     print(f"calling process user input for {msg}")
    #     beneficiary_bot.process_user_input(update, context)
    beneficiary_bot.all_done(update,context)
    return 'ok'

@app.route('/api/v1/users')
@crossdomain(origin='*', debug=app.debug)
def get_valid_users():

    return json.dumps([
        {
            'id': u.chat_id,
            'first_name': u.first_name,
            'last_name': u.last_name
        }
        for u in db.session.query(User.first_name, User.last_name, User.chat_id)])


@app.route('/api/v1/user/<chat_id>')
@crossdomain(origin='*', debug=app.debug)
def get_user(chat_id):

    return json.dumps([
        {
            'id': u.chat_id,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'aww': u.aww,
            'child_name': u.child_name,
            'child_birthday': u.child_birthday
        }
        for u in db.session.query(
            User.first_name,
            User.last_name,
            User.chat_id,
            User.child_birthday,
            User.child_name,
            User.aww)],
        default=json_serial)


@app.route('/api/v1/messages/<chat_id>')
@crossdomain(origin='*', debug=app.debug)
def show_user_messages(chat_id):
    return json.dumps([
        {
            'id': m.id,
            'source': m.source,
            'chat_id': m.chat_id,
            'state': m.state,
            'text': m.msg,
            'server_time': m.server_time
        }
        for m in db.session.query(
            Message.id,
            Message.source,
            Message.chat_id,
            Message.msg,
            Message.state,
            Message.server_time
        ).filter(Message.chat_id == chat_id)],
        default=json_serial)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
