from dataclasses import replace

from shorts_agent import niche
from shorts_agent.props_agent import exports_of, static_check as props_check
from shorts_agent.storyboard_agent import static_check
from shorts_agent.styles import STYLES

ST = replace(STYLES["history"], props_mode="generate", props_required=("stadium",))


def make(n=9, head="import { ctx, W, H } from './lib.js';\nimport { cut } from './kit.js';\n", extra=""):
    fns = "".join(f"export function {'stadium' if i == 0 else f'p{i}'}(x, y, s = 1, t = 0, o = {{}}) {{ ctx.save(); ctx.restore(); }}\n" for i in range(n))
    return head + "export const NC = {};\nexport function backdrop(t = 0, o = {}) { ctx.fillRect(0, 0, W, H); }\n" + fns + extra + "// pad\n" * 60


def test_good_props_pass():
    assert props_check(make(), ST) == []


def test_props_problems_are_reported():
    assert any("not allowed" in p for p in props_check(make(head="import x from './props.js';\n"), ST))
    assert any("backdrop" in p for p in props_check(make().replace("export function backdrop", "function backdrop"), ST))
    assert any("Math.random" in p for p in props_check(make(extra="const r = Math.random();\n"), ST))
    assert any("stadium" in p for p in props_check(make().replace("stadium", "arena"), ST))
    assert any("at least" in p for p in props_check(make(n=3), ST))


def test_exports_of(tmp_path):
    f = tmp_path / "np.js"
    f.write_text(make())
    assert {"backdrop", "stadium", "p1"} <= exports_of(f) and "NC" not in exports_of(f)


def sb(body, imports="import * as NP from './core/niche_props.js';\n"):
    return imports + "export function buildShots() {\n  const S = [], CUES = [];\n" + body + "  return { shots: S, cues: CUES };\n}\n" + "// pad\n" * 60


def test_generated_mode_needs_the_np_import():
    assert any("niche_props" in p for p in static_check(sb("", imports=""), ST, 2))


def test_generated_mode_rejects_unknown_np_and_historical_sc():
    probs = static_check(sb("NP.backdrop(t); NP.ghost(1, 2, 3, t);\n" * 4), ST, 2, names={"NP": {"backdrop"}})
    assert any("NP.ghost" in p for p in probs)
    imp = "import * as NP from './core/niche_props.js';\nimport * as SC from './core/props.js';\n"
    probs = static_check(sb("NP.backdrop(t); SC.house(1, 2, 3);\n" * 3, imports=imp), ST, 2, names={"NP": {"backdrop"}})
    assert any("SC.house" in p for p in probs)
    # allowed effect (SC.rain) plus enough NP calls (4 >= 2 * 2 lines): no problems
    assert not static_check(sb("NP.backdrop(t); SC.rain(t);\n" * 4, imports=imp), ST, 2, names={"NP": {"backdrop"}})

def test_props_section_is_validated():
    base = niche.load("history")
    assert niche.validate("x", {**base, "props": {"mode": "generate"}}) != []
    assert niche.validate("x", {**base, "props": {"mode": "magic"}}) != []
    assert niche.validate("x", {**base, "props": {"mode": "generate", "theme": "Cricket", "required": ["bat"]}}) == []