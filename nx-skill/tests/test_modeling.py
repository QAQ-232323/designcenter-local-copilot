"""Intent routing, plan schema and drawing rules."""

from __future__ import annotations

import pytest

from nx_skill.modeling import is_visual_prompt, plan_template, route_intent, visual_spec


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Create a flange plate with 6 bolt holes", "modeling"),
        ("建模一个减速器箱体", "modeling"),
        ("extrude this sketch and add fillets", "modeling"),
        ("Run a linear static stress analysis with a mesh", "simulation"),
        ("对这个零件做有限元仿真，施加边界条件", "simulation"),
        ("solve the modal analysis and post-process", "simulation"),
    ],
)
def test_routing(prompt, expected):
    assert route_intent(prompt).name == expected


def test_route_reports_why_it_won():
    intent = route_intent("extrude a sketch and fillet the edges")
    assert intent.score > 0
    assert intent.matched
    assert intent.primary_modules == ("NXOpen", "NXOpen.Features")
    assert intent.nx_application == "UG_APP_MODELING"


def test_an_empty_prompt_defaults_to_modelling_but_with_no_confidence():
    intent = route_intent("")
    assert intent.name == "modeling"
    assert intent.score == 0


def test_alternatives_are_reported():
    intent = route_intent("create a solid and then mesh it for analysis")
    assert intent.alternatives


@pytest.mark.parametrize(
    "prompt",
    ["三视图建模", "build from this image", "根据工程图建个零件", "orthographic drawing", "识图"],
)
def test_visual_prompts_are_detected(prompt):
    assert is_visual_prompt(prompt) is True


def test_non_visual_prompts_are_not_flagged():
    assert is_visual_prompt("create a 100mm cube") is False


def test_plan_uses_the_naming_convention():
    plan = plan_template("make a bracket", part_name="Bracket")
    examples = plan["namingConvention"]["examples"]
    assert examples[0].startswith("01_Bracket_")
    assert "03_Base_Extrude" in examples
    assert plan["partNavigatorPolicy"]["mustUse"]


def test_plan_attaches_the_visual_policy_only_when_relevant():
    assert "visualModelingPolicy" not in plan_template("make a cube")
    visual = plan_template("build from this three-view drawing")
    assert "visualModelingPolicy" in visual


def test_plan_part_name_is_sanitised():
    assert plan_template("x", part_name="My Part")["partName"] == "My_Part"
    assert plan_template("x", part_name="   ")["partName"] == "NX_Model"


def test_visual_spec_covers_projection_conventions():
    spec = visual_spec("三视图", projection_system="first_angle")
    assert spec["projectionSystem"]["requested"] == "first_angle"
    rules = " ".join(spec["projectionSystem"]["rules"])
    assert "first-angle" in rules.lower()
    assert "third-angle" in rules.lower()
    assert spec["viewExtractionChecklist"] and spec["validationChecklist"]
