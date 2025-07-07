import struct

class Unpacker:
    def __init__(self, data):
        self.data = data
        self.offset = 0
    def left(self):
        left = len(data) - self.offset
        if left < 0:
            left = 0
        return left
    def unpack(self, format):
        format = '<' + format
        size = struct.calcsize(format)
        try:
            result = struct.unpack_from(format, self.data, self.offset)
        except struct.error as err:
            raise NoDataError(size, self.left(), self.offset) from err
        self.offset += size
        return result if len(result) != 1 else result[0]
    def expect(self, format, expected):
        actual = self.unpack(format)
        if actual != expected:
            raise UnexpectedError(expected, actual)
    def byte(self):
        try:
            result = self.data[self.offset]
        except IndexError as err:
            raise NoDataError(1, self.left(), self.offset) from err
        self.offset += 1
        return result
    def bytes(self, length):
        result = self.data[self.offset : self.offset + length]
        if len(result) < length:
            raise NoDataError(length, self.left(), self.offset)
        self.offset += length
        return result
    def skip(self, length):
        self.offset += length

class NoDataError(Exception):
    def __init__(self, offset, requested, available):
        super().__init__(offset, requested, available)
        self.offset = offset
        self.requested = requested
        self.available = available
    def __str__(self):
        return f'requested {self.requested} bytes, {self.available} available (offset {self.offset:#010x})'

class UnexpectedError(Exception):
    def __init__(self, expected, actual):
        super().__init__(expected, actual)
        self.expected = expected
        self.actual = actual
    def __str__(self):
        return f'expected {self.expected}, got {self.actual}'
