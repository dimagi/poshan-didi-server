from enum import IntEnum, unique
from rasa_nlu.model import Interpreter
from simple_settings import settings

# where model_directory points to the model folder
interpreter = Interpreter.load('models/current/nlu')


@unique
class Intent(IntEnum):
    UNKNOWN = -1
    GREET = 0
    ONE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10,
    YES = 11,
    NO = 12,


ENTITY_MAP = {
    "one": Intent.ONE,
    "two": Intent.TWO,
    "three": Intent.THREE,
    "four": Intent.FOUR,
    "five": Intent.FIVE,
    "six": Intent.SIX,
    "seven": Intent.SEVEN,
    "eight": Intent.EIGHT,
    "nine": Intent.NINE,
    "ten": Intent.TEN,
}


def get_intent(msg):
    result = interpreter.parse(msg)

    # A bit of a cheat, but we'll take entities over anything
    if len(result['entities']) > 0:
        try:
            return ENTITY_MAP[result['entities'][0]['value']]
        except KeyError:
            return Intent.UNKNOWN

    if result['intent']['confidence'] < settings.NLU_THRESHOLD:
        return Intent.UNKNOWN
    elif result['intent']['name'] == 'greet':
        return Intent.GREET
    elif result['intent']['name'] == 'yes':
        return Intent.YES
    elif result['intent']['name'] == 'no':
        return Intent.NO
    elif result['intent']['name'] == 'option':
        return ENTITY_MAP[result['entities'][0]['value']]
    return Intent.UNKNOWN


def test_nlu_loop():
    sentence = input(
        'Enter a sentence and I will tell you the intent (-1 or ctrl-c to quit):\n')
    while sentence != '-1':
        print(f'Intent result: {get_intent(sentence)}')
        print(interpreter.parse(sentence))
        sentence = input(
            'Enter a sentence and I will tell you the intent (-1 or ctrl-c to quit):\n')


if __name__ == '__main__':
    test_nlu_loop()
