"""Provides interfaces for accessing individual bits and bit ranges of an 
integer numbers.

Classes:
    Bitfield - base class for bitfields
    named - helper class for making named fields

Functions:
    make - helper function to type less
"""

__all__ = ('Bitfield', 'named', 'make')

class Bitfield:
    """Provides interface to access individual bits and bit ranges of a number."""
    def __init__(self, value: int):
        """Initializes bitfield.

        Positional arguments:
            value: initial of bitfield
        """
        self.all = value
    def __getitem__(self, key: int | slice):
        """Allows for reading individual bits or ranges.

        bf[3] - for accessing individual bits
        bf[7:3] or bf[3:7] - for accessing ranges
        Note: ranges are inclusive. bf[7:3] returns FOUR bits, from bit 7 to 
        bit 3 INCLUSIVELY.
        """
        lower, upper = order_bounds(*process_key(key))
        return get(value=self.all, mask=mask(lower, upper), shift=lower)
    def __setitem__(self, key: int | slice, value: int)
        """Allows for writing individual bits or ranges.

        bf[3] - for accessing individual bits
        bf[7:3] or bf[3:7] - for accessing ranges
        Note: ranges are inclusive. bf[7:3] returns FOUR bits, from bit 7 to 
        bit 3 INCLUSIVELY.
        """
        lower, upper = order_bounds(*process_key(key))
        self.all = set(value=self.all, mask=mask(lower, upper), shift=lower, field=value)
    def __eq__(self, other):
        return self.all == other.all
    def __hash__(self):
        return hash(('bitfield', self.all))
    def copy(self):
        return type(self)(self.all)

class named:
    """Provides a way to add named bitfields.

    This class is to be used ONLY with classes inherited from Bitfield.

    Usage is as follows:
        class YourBitfield(bitfield.Bitfield):
            foo = bitfield.named[3:0]
            bar = bitfield.named[7:4]

        ybf = YourBitfield(26)
        ybf.foo  # same as ybf[3:0]
        ybf.bar  # same as ybf[7:4]
    """
    def __init__(self, a: int, b: int, /):
        lower, upper = order_bounds(a, b)
        self.shift = lower
        self.mask = mask(lower, upper)
    def __class_getitem__(cls, key: int | slice):
        a, b = process_key(key)
        return cls(a, b)
    def __get__(self, instance: Bitfield, owner):
        return get(value=instance.all, mask=self.mask, shift=self.shift)
    def __set__(self, instance: Bitfield, value: int):
        instance.all = set(value=instance.all, mask=self.mask, shift=self.shift, field=value)

def make(value: int):
    """Helper function to create bitfield objects."""
    return Bitfield(value)

###############################################################################
# HELPERS
###############################################################################

def process_key(key) -> tuple[int, int]:
    """Verifies bitfield getitem key, returns lower and upper bound of bit range."""
    if type(key) is int:
        a = key
        b = key
    elif type(key) is slice:
        if key.step is not None:
            raise IndexError('bitfields cannot be indexed with a step')
        a = key.start
        b = key.stop
    else:
        raise IndexError(f'bitfields cannot be indexed with objects of type {type(key)}')
    return a, b

def order_bounds(a: int, b: int) -> tuple[int, int]:
    """Returns ordered pair of arguments."""
    return min(a, b), max(a, b)

def mask(lower: int, upper: int) -> int:
    """Returns mask that is as wide as difference between lower and upper."""
    return (1 << (upper - lower + 1)) - 1

def get(value: int, mask: int, shift: int) -> int:
    """Returns bits of value specified by mask and shift."""
    return (value >> shift) & mask

def set(value: int, mask: int, shift: int, field: int):
    """Replaces bits in a value.

    Suppose we want to replace value
        VVVVVVVVVVVVV (bit representation)
    with value
        VVVVVFFFFFVVV

    That can be done with specified arguments
        value: VVVVVVVVVVVVV
        mask:  0000000011111
        shift: 3
        field: ________FFFFF

    Positional/keyword arguments:
        value - the source value to replace bits within
        mask - specifies the width of replaced bits
        shift - specifies the position of mask within value
        field - contains bits to be replaced with

    Returns value with replaced bits.
    """ 
    value &= ~(mask << shift)
    value |= (field & mask) << shift
    return value
