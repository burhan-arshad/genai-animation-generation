from shorts_agent import script_agent as S
from shorts_agent.schemas import Line, ScriptDraft


def draft(n_lines=9, words=11):
    return ScriptDraft(title="t", sources=["a"], lines=[Line(text=" ".join(["word"] * words)) for _ in range(n_lines)])


def test_style_notes_alone_are_acceptable():
    assert S.acceptable(draft(), ["Narration has 99 words; target is 100-125.",
                                  "The last line must echo a key word of the opening (a loop) or end with a question to the viewer."])


def test_fact_and_topic_problems_are_never_accepted():
    assert not S.acceptable(draft(), ["Line 3: number 1965 is not stated in cited evidence ['E1']. Use only numbers present in the evidence, or leave the number out."])
    assert not S.acceptable(draft(), ["The script must be about 'X': it never mentions x."])


def test_a_script_that_is_far_too_short_is_not_accepted():
    assert not S.acceptable(draft(n_lines=4, words=5), ["Narration has 20 words; target is 100-125."])


def test_evidence_is_interleaved_across_pages():
    items = [{"url": "a", "text": str(i)} for i in range(4)] + [{"url": "b", "text": "x"}, {"url": "c", "text": "y"}]
    assert [e["url"] for e in S.interleave(items)][:3] == ["a", "b", "c"]