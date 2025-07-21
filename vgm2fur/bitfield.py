def _order_bounds(a, b):
    return min(a, b), max(a, b)

def _process_bitfield_key(key):
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

def _get_mask(lower, upper):
    return (1 << (upper - lower + 1)) - 1

def _get_field(value, mask, shift):
    return (value >> shift) & mask

def _set_field(value, mask, shift, field):
    value &= ~(mask << shift)
    value |= (field & mask) << shift
    return value

class Bitfield:
    def __init__(self, initial=0):
        self.value = initial
    def __getitem__(self, key):
        lower, upper = _order_bounds(*_process_bitfield_key(key))
        return _get_field(self.value, _get_mask(lower, upper), lower)
    def __setitem__(self, key, value):
        lower, upper = _order_bounds(*_process_bitfield_key(key))
        self.value = _set_field(self.value, _get_mask(lower, upper), lower, value)
    def __eq__(self, other):
        return self.value == other.value
    def __hash__(self):
        return hash(('bitfield', self.value))
    def copy(self):
        T = type(self)
        return T(self.value)
    def __repr__(self):
        return f'(bitfield){f.value}'

    @property
    def all(self):
        return self.value
    @all.setter
    def all(self, value):
        self.value = value

class named:
    def __init__(self, a, b):
        lower, upper = _order_bounds(a, b)
        self.shift = lower
        self.mask = _get_mask(lower, upper)
    def __class_getitem__(cls, key):
        a, b = _process_bitfield_key(key)
        return cls(a, b)
    def __get__(self, instance, owner):
        return _get_field(instance.value, self.mask, self.shift)
    def __set__(self, instance, value):
        instance.value = _set_field(instance.value, self.mask, self.shift, value)

def make(n):
    return Bitfield(n)

def join(*args):
    n = 0
    shift = 0
    for arg in args:
        n = (arg & 0xFF) << shift
        shift += 8
    return Bitfield(n)
