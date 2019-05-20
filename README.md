# Poshan Didi Bot

This is the README for the Poshan Didi telegram bot. This repository has two python applications in it:

* A Flask-based application that provides a very lightweight API for accessing users and messages captured by the system
* A Telegram bot that serves the Poshan Didi bot

It is likely bad form to have both of these in the same repo, but this is research and it is the easiest way to share the `db.py` file between the two.

**Scripts are written with Python 3.6+**


## Getting started


### Setup virtualenv

Make a Python 3.6+ `virtualenv` and enter it.

With `virtualenvwrapper`:

`mkvirtualenv --no-site-packages -p python3.6 poshan-didi`

### Install requirements

`pip install -r requirements.txt`

### Local settings

For local settings, we use the `simple-settings` library. Note: This is used by the **telegram bot and the Flask server** because of the database credentials.

To get a local settings file first `cp settings_sample.py localsettings.py`.

When running code you should use a command-line or environment variable such as:

```sh
$ python script.py --settings=localsettings
```

or

```sh
$ SIMPLE_SETTINGS=localsettings python script.py
```

#### Customizing settings

You will need to specify the `TELEGRAM_TOKEN` for your bot, the `NURSE_CHAT_ID` that corresponds to the Telegram account you want to escalate messages up to, and--optionally--the `DB_SQLALCHEMY_CONNECTION` string for the database you want to use to store users and messages. 

The `TELEGRAM_TOKEN` comes from the `BotFather` when you initially create your telegram bot.

The `NURSE_CHAT_ID` is the Telegram `chat_id` for the Telegram account that you want to escalate messages to. If you do not know this ahead of time, you can leave it as is and start the bot (after completing the steps below). Once the bot is started, send a message from the account that you want to use for the nurse. The message will be processed as a user message because the `chat_id` does not match the previously set `NURSE_CHAT_ID`. Check the log file or the database to find the `chat_id` for this account. Set the `NURSE_CHAT_ID`, restart the bot, and test that escalation is happening correctly.

### Setup the database

Before running the bot or the flask server, it is necessary to create the database. At the moment, this is a sqlite flat file, but you can modify this easily. Use the `DB_SQLALCHEMY_CONNECTION` settings parameter to put in a valid SQLAlchemy connection string.

Before running the aplpication for the first time, import the `db` module from a standalone terminal and run the `reset_db()` command. For example:

```sh
$ SIMPLE_SETTINGS=localsettings ipy
```
```python
In [1]: from db import Database

In [2]: Database().reset_db()
```

## Running the Flask server

### Development mode

To run the Flask server in development mode, which allows auto-reloading based on changes and additional debug output, use the following command:

```sh
$ SIMPLE_SETTINGS=localsettings FLASK_APP=app.py FLASK_DEBUG=1 python -m flask run
```

### Production

TBD

## Running the telegram bot

### Building the NLU models

The telegram bot we built relies on the RASA-NLU package to do very basic NLU on incoming messages to determine the intent of incoming messages. This is overkill for initial purposes, but lays the ground work for complex NLU. The library requires that we build models based on the training data before it can be used. To do that, run the following command:

```sh
$ python -m rasa_nlu.train -c nlu_config.yml --data data/nlu-training-data.json -o models --fixed_model_name nlu --project current --verbose
```

This process should complete relatively quickly and will produce a folder called `models` that contains the training data from the NLU library.

### Running the bot

Once you have built the models and setup the database, you can run the bot, use the following command:

```sh
$ SIMPLE_SETTINGS=localsettings python poshan_didi_bot.py
```
