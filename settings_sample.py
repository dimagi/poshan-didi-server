import logging
import os

# This file contains settings and configuration all mixed up together.

# Logging customization
LOG_FILENAME = 'poshan_didi.log'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.INFO

# Telegram setup
TELEGRAM_TOKEN = 'TOKEN_ID'
# The telegram chatid with your bot for the escalation messages
NURSE_CHAT_ID = 12345

# Database setup
DB_SQLALCHEMY_CONNECTION = 'sqlite:///poshan_didi.db'


# NLU threshold -- NLP engine must have confidence above threshold to
# return an intent
NLU_THRESHOLD = 0.4

# State machine files
FLOW_6_MONTHS = os.path.join('data', 'poshan-didi-6months.json')
FLOW_12_MONTHS = os.path.join('data', 'poshan-didi-12months.json')
TRANSLATIONS_6_MONTHS = os.path.join(
    'data', 'poshan-didi-translations-6months.csv')
TRANSLATIONS_12_MONTHS = os.path.join(
    'data', 'poshan-didi-translations-12months.csv')

# state machine timeout
STATE_TIMEOUT_MINUTES = 30

# Should this be in Hindi?
HINDI = False

# GOD Mode chat ID
GOD_MODE = 0
