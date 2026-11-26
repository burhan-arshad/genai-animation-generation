"""Hooks: the first two lines decide whether a viewer stays, the last line decides whether he replays, shares or comments.
This module owns (1) a library of different hook and ending formulas, (2) the choice of a formula that was NOT used in the last videos,
(3) code checks that reject generic hooks and weak endings, so the writer must retry. Nothing here calls an LLM."""
from __future__ import annotations

import random
import re
import os
from pathlib import Path

HOOKS = {
    "cold_open": ("Start in the middle of the most dramatic moment, as if the story already began; explain nothing yet.",
                  "The stone man was already out of the ground. And the whole town was lying."),
    "impossible_fact": ("State one hard, specific fact that sounds false (a number, a price, a size). The fact must be in the evidence.",
                        "A farmer paid for a giant. The giant was made of gypsum."),
    "wrong_belief": ("Attack a common belief with a short blunt correction, then promise the real story.",
                     "Nobody found it. It was put there. And that was the plan."),
    "countdown": ("Put a clock, a deadline or a number of days on the screen: something is about to happen and we know it.",
                  "He had one year to keep a secret. It was buried twelve feet away."),
    "absurd_reason": ("Name the ridiculous reason first, the consequence second. The smaller the reason, the better.",
                      "It all started because a man lost an argument."),
    "mystery_box": ("Name the thing we will learn at the very end, without revealing it ('and the reason is...').",
                    "This giant fooled thousands. And the way he was caught is almost funnier."),
    "challenge": ("Speak to the viewer in second person: you would have fallen for it too / you would have paid.",
                  "You would have paid to see it. Thousands did."),
    "contrast": ("Two facts that cannot both be true, side by side: the rich and the broke, the hero and the fraud.",
                 "One man got rich. The other got the blame. Same stone."),
    "missing_piece": ("Start from something missing, hidden, buried, banned or lost, and let the question be where it went.",
                      "For a whole year, nobody knew what was underground."),
    "last_seen": ("Start on the last confirmed, ordinary moment before everything went wrong: a time, a place, a person doing something normal.",
                  "At six that evening, the lamp on deck was still lit. By morning, the ship was empty."),
    "one_clue": ("Open on the single strangest clue or object and say nothing about what it means.",
                 "They found his coat folded neatly on the shore. Inside the pocket was one torn page."),
}
ENDINGS = {
    "loop_callback": ("Final line echoes the first line's key word or image with a twist, so the video replays into itself.",
                      "And that is how a man lost an argument and won a giant."),
    "comment_bait": ("Final line is a short question to the viewer that people want to answer in the comments (would you / which / who).",
                     "Honestly, would you have paid to see it?"),
    "irony_punchline": ("Final line is a dry ironic one-liner that flips the meaning of the whole story.",
                        "The fake giant outlived the real stories."),
    "reveal_last": ("Hold the single most surprising fact back and deliver it as the very last line.",
                    "And the man who made it never even took credit."),
    "today_twist": ("Final line connects the story to today in one surprising present-tense fact (only if it is in the evidence).",
                    "Today, people still line up to look at it."),
    "open_question": ("Final line is the unanswered question of the case, short, so viewers want to answer it in the comments.",
                      "So what really happened on that deck?"),
    "clue_that_solved_it": ("Final line delivers the small detail that cracked the case and echoes the opening clue.",
                            "One torn corner of paper was all it took."),
}

GENERIC = re.compile(r"^\s*(did you know|welcome|today we|today i|in this video|have you ever|let me tell|hey guys|hey everyone|what if i told|you won'?t believe|"
                     r"here'?s the story|this is the story|this is the tale|imagine this|picture this|once upon|so, |ok(ay)?,? so|let'?s talk|let'?s dive|let'?s get)", re.I)
STOP = set("the a an of in on at to for and or with from by is was were that this its their his her him them it he she they we you i not no but so then than as be are had has have "
           "who what when where why how all one into out up down over under after before about just also even still only very more most".split())
TURNS = re.compile(r"^\s*(but|then|until|except|yet|suddenly|meanwhile|so|and then|and yet|still|instead|worse|even|now)\b", re.I)
NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion".split())


def job_id_of(project: Path) -> int | None:
    m = re.match(r"(\d+)-", Path(project).name)
    return int(m.group(1)) if m else None


def pick(recent_hooks: list[str], recent_ends: list[str], seed: int = 0, weights: dict | None = None) -> tuple[str, str]:
    """A hook formula and an ending formula that were not used in the last videos. With `weights` (from the channel's stats) the better one is preferred,
    except for LEARN_EXPLORE percent of the picks, which stay random so the channel keeps trying new things."""
    rnd = random.Random(seed * 7919 + 13)
    explore = float(os.getenv("LEARN_EXPLORE", "25") or 25) / 100

    def choose(pool: dict, recent: list[str], keep: int, w: dict | None = None) -> str:
        fresh = [k for k in pool if k not in recent[:keep]]
        if not fresh:
            fresh = [k for k in pool if k != (recent[0] if recent else None)] or list(pool)
        if w and rnd.random() >= explore:
            ranked = sorted((k for k in fresh if k in w), key=lambda k: -w[k])
            if ranked:
                return ranked[0]
        age = {k: (recent.index(k) if k in recent else 99) for k in fresh}
        best = max(age.values())
        return rnd.choice([k for k in fresh if age[k] == best])

    w = weights or {}
    return choose(HOOKS, recent_hooks, 4, w.get("hooks")), choose(ENDINGS, recent_ends, 2, w.get("ends"))


def formula_text(hook: str, end: str) -> str:
    h = (f"HOOK FORMULA for this video: {hook}: {HOOKS[hook][0]} Example of the feeling (another story, never copy it): \"{HOOKS[hook][1]}\"\n"
         if hook in HOOKS else "")
    return h + f"ENDING FORMULA for this video: {end}: {ENDINGS[end][0]} Example of the feeling (another story, never copy it): \"{ENDINGS[end][1]}\""

RULES = """HOOK AND RETENTION RULES (strict, they decide whether people watch to the end):
- Line 1 is the cold open: 12 words or fewer, a concrete person, thing, number or place, and it must make the viewer ask a question that is NOT answered until the last third.
  Never open with 'Did you know', 'Welcome', 'Today', 'Have you ever', 'Imagine', 'In this video', 'You won't believe' or any greeting.
- Line 2 raises the stakes or deepens the question (a stranger fact, a deadline, a contradiction). Do NOT explain it yet.
- Then go back and tell the story in order. Every 2-3 lines there is a TURN: a line that starts with But, Then, Until, Except, Yet, Suddenly or So and changes what we thought.
- The most surprising fact of the whole story is kept for the final third. Never give away the answer to the hook before it.
- The last line is 12 words or fewer, pays off the hook, shares a key word with the opening, and makes the viewer want to replay or comment.
- Short sentences. Spoken, not written. No filler ('basically', 'actually', 'literally')."""


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']{4,}", text.lower()) if w not in STOP}


def check(lines: list[str]) -> list[str]:
    """Code checks on the spoken lines (digits already turned into words). Empty list = the hook and the ending pass."""
    problems: list[str] = []
    if len(lines) < 6:
        return problems
    first = lines[0].strip()
    if GENERIC.search(first):
        problems.append("Line 0 is a generic opener. Start with a concrete person, thing, number or place: the most dramatic moment of the story.")
    if len(first.split()) > 14:
        problems.append(f"Line 0 has {len(first.split())} words: the cold open must be 12 words or fewer.")
    toks = first.replace(",", " ").split()
    concrete = any(t.lower().strip(".,!?") in NUMBER_WORDS for t in toks) or any(t[:1].isupper() for t in toks[1:]) or len(toks) >= 3 and any(len(t) >= 6 for t in toks)
    if not concrete:
        problems.append("Line 0 is vague: name a person, a place, a thing or a number.")
    head = " ".join(lines[:2]).lower()
    if re.search(r"\b(because|the reason|turns out|it was a (hoax|fake|lie|trick))\b", head) and not re.search(r"\?|\b(why|how)\b", head):
        problems.append("Lines 0-1 give the answer away. Keep the answer for the last third and only raise the question.")
    last = lines[-1].strip()
    if len(last.split()) > 14:
        problems.append(f"The last line has {len(last.split())} words: 12 or fewer.")
    if not (content_words(last) & content_words(" ".join(lines[:4]))) and "?" not in last:
        problems.append("The last line must echo a key word of the opening (a loop) or end with a question to the viewer.")
    body = lines[2:-1]
    turns = sum(1 for l in body if TURNS.search(l))
    need = max(1, len(body) // 5)
    if turns < need:
        problems.append(f"Only {turns} turn line(s) in the story: at least {need} lines must start with But, Then, Until, Except, Yet, Suddenly or So and change what we thought.")
    return problems

CONTRAST = re.compile(r"\b(but|yet|never|nobody|no one|nothing|none|empty|missing|vanished|gone|still|only|without|impossible|unsolved|unknown|why|how|what|who)\b", re.I)
YEAR_FIRST = re.compile(r"^\s*(in|on|during|by|back in|around|since)\s+(the\s+year\s+)?(\d{3,4}|(fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\b|"
                        r"(january|february|march|april|may|june|july|august|september|october|november|december)\b)", re.I)


def hook_ok(line0: str, line1: str = "") -> str:
    """'' when the two opening lines can be used, else the reason."""
    if not 3 <= len(line0.split()) <= 12:
        return "line 0 must have 3-12 words"
    if GENERIC.search(line0):
        return "generic opener"
    both = (line0 + " " + line1).lower()
    if re.search(r"\b(because|the reason|turns out)\b", both) and not re.search(r"\?|\b(why|how)\b", both):
        return "gives the answer away"
    return ""


def score_hook(line0: str, line1: str = "") -> int:
    """How likely the two opening lines are to stop a thumb: short, concrete, a contradiction, not an exposition that starts with a year."""
    w, s = line0.split(), 0
    if len(w) <= 10:
        s += 2
    elif len(w) <= 12:
        s += 1
    if re.search(r"\d", line0) or any(t.lower().strip(".,!?") in NUMBER_WORDS for t in w):
        s += 1
    if CONTRAST.search(line0):
        s += 2
    if any(t[:1].isupper() for t in w[1:]):
        s += 1
    if line0.strip().endswith("?"):
        s += 1
    if YEAR_FIRST.search(line0):
        s -= 3
    if CONTRAST.search(line1) or "?" in line1:
        s += 1
    return s