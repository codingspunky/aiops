import pytest
from aiops.app.utils import reverse_string

@pytest.mark.parametrize(
    "input_str,expected",
    [
        ("hello", "olleh"),
        ("", ""),
        ("A", "A"),
        ("racecar", "racecar"),
        ("12345", "54321"),
    ],
)
def test_reverse_string(input_str: str, expected: str) -> None:
    assert reverse_string(input_str) == expected
