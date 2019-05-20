
class Singleton(type):
    """Simple metaclass that turns a class into a singleton. To use it define
    your class with this set as the metaclass. For example:

    class MyNewClass(metaclass=Singleton):
        ...
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
