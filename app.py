from datetime import date, datetime, timedelta

import json
import os
from flask import Flask, render_template, request, make_response, current_app
from functools import update_wrapper

from db import User, Message, Database

app = Flask(__name__)
db = Database()

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
            'text': m.msg,
            'server_time': m.server_time
        }
        for m in db.session.query(
            Message.id,
            Message.source,
            Message.chat_id,
            Message.msg,
            Message.server_time
        ).filter(Message.chat_id == chat_id)],
        default=json_serial)
