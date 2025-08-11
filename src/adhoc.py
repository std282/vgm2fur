"""Provides functions for defining things on the fly!"""

def exception(name, msg, base=Exception):
    """Returns exception class with specified name and error message.

    Error message will be the result of mag.format(*args). This settles two
    things:
        1. Message may contain format placeholders of type {0}, {1}, etc.
        2. It is raiser's responsibility to make sure that the exception
           is created with number of arguments sufficient for format method
           to succeed.

    Optional base argument may be specified to provide a base exception class.
    """
    assert issubclass(base, Exception)
    def _str(self):
        return msg.format(*self.args)
    return type(name, (base,), dict(__str__=_str))

def warning(name, msg, base=UserWarning):
    """Returns warning class with specified name and error message.

    Warning message will be the result of mag.format(*args). This settles two
    things:
        1. Message may contain format placeholders of type {0}, {1}, etc.
        2. It is raiser's responsibility to make sure that the warning
           is created with number of arguments sufficient for format method
           to succeed.

    Optional base argument may be specified to provide a base warning class.
    """
    assert issubclass(base, Warning)
    return exception(name, msg, base=base)
