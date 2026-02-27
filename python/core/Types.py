from enum import Enum, auto
from typing import Any

class PortDirection(Enum):
    INPUT = auto()
    OUTPUT = auto()
    INPUT_OUTPUT = auto()

class PortFunction(Enum):
    DATA = auto()
    CONTROL = auto()

class ValueType(Enum):
    ANY = "any"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    BOOL = "bool"
    DICT = "dict"
    ARRAY = "array"
    OBJECT = "object"
    VECTOR = "vector"
    MATRIX = "matrix"
    COLOR = "color"
    BINARY = "binary"
    
    @staticmethod
    def validate(value: Any, data_type: 'ValueType') -> bool:
        from collections import OrderedDict
        if data_type == ValueType.ANY:
            return True
        if value is None: 
            return True # Allow None? Or strictly enforce?
            
        if data_type == ValueType.INT:
            return isinstance(value, int)
        elif data_type == ValueType.FLOAT:
            return isinstance(value, (float, int)) # Allow ints to pass as floats
        elif data_type == ValueType.STRING:
            return isinstance(value, str)
        elif data_type == ValueType.BOOL:
            return isinstance(value, bool)
        elif data_type == ValueType.DICT:
            return isinstance(value, (dict, OrderedDict))
        elif data_type == ValueType.ARRAY:
            return isinstance(value, (list, tuple))
        elif data_type == ValueType.OBJECT:
            return True # Or specific class check
        elif data_type == ValueType.VECTOR:
            return isinstance(value, (list, tuple)) # Simplistic check for now
        elif data_type == ValueType.MATRIX:
            return isinstance(value, (list, tuple)) # Simplistic check
        elif data_type == ValueType.COLOR:
            return isinstance(value, (str, tuple, list)) # Hex string or RGB tuple
        elif data_type == ValueType.BINARY:
            return isinstance(value, (bytes, bytearray))
            
        return False

class NodeKind(Enum):
    FUNCTION = auto()
    NETWORK = auto()