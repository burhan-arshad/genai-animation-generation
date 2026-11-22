import pytest

from shorts_agent.schemas import Line, ScriptDraft, check_script, repair_numbers, speak_numbers
from shorts_agent.styles import STYLES


@pytest.mark.parametrize("src,out", [
    ("In 1869, workers dug a well", "In eighteen sixty-nine, workers dug a well"),
    ("It was 10 feet tall", "It was ten feet tall"),
    ("a 10-foot giant", "a ten-foot giant"),
    ("He paid $25 and $2.50", "He paid twenty-five dollars and two dollars and fifty cents"),
    ("the 3rd show and the 21st", "the third show and the twenty-first"),
    ("about 50% of 3,000 people", "about fifty percent of three thousand people"),
    ("In 1905 and 1900 and 2007 and 2024", "In nineteen oh five and nineteen hundred and two thousand seven and twenty twenty-four"),
    ("the 1860s were wild", "the eighteen sixties were wild"),
    ("2,600 miles and 1500 pounds", "two thousand six hundred miles and one thousand five hundred pounds"),
    ("a 2.5 mile walk", "a two point five mile walk"),
    ("nothing to change here", "nothing to change here"),
])
def test_speak_numbers(src, out):
    assert speak_numbers(src) == out


def test_repair_makes_the_script_pass_the_digit_check():
    st = STYLES["history"]
    d = ScriptDraft(title="t", sources=["a", "b"], lines=[Line(text=f"In 1869 and 10 feet number {i} word " * 1 + "x y z", caps="") for i in range(12)])
    assert any("numbers" in p for p in check_script(d, st))
    assert not any("numbers" in p for p in check_script(repair_numbers(d), st))
