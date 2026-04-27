# test_my_math.py
import pytest
from my_math import add, divide


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0

def test_divide():
    assert divide(10, 2) == 5
    with pytest.raises(ValueError):
        divide(10, 0)