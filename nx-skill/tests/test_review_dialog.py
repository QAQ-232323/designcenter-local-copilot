r"""Validate the shipped Block Styler dialog definition.

\`.dlx\` files are opaque: NX fails late and unhelpfully if one is malformed, and
the only place a user finds out is inside NX. These checks catch the mistakes
that are actually likely when a dialog is assembled programmatically -- a block
whose id and BlockID disagree, a leftover id from the vendor sample it was cloned
from, or a missing property -- without needing NX at all.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

DIALOG_PATH = Path(__file__).resolve().parents[1] / "nx_runtime" / "application" / "nx_review_executor.dlx"

#: Blocks the executor addresses by id at runtime. If one is renamed here without
#: updating the executor, the dialog opens with a block the code cannot find.
EXPECTED_BLOCKS = {
    "status_label": "UICOMP_label",
    "step_list": "UICOMP_list_box",
    "run_next": "UICOMP_button",
    "undo_last": "UICOMP_button",
    "run_auto": "UICOMP_button",
    "refresh": "UICOMP_button",
}

#: Ids from the vendor sample the document skeleton was cloned from. Any of these
#: surviving means the renaming was incomplete and the dialog is probably broken.
STALE_IDS = (
    "ExpressionList",
    "ButtonGetExpressions",
    "FeatureList",
    "GroupFeatureSelection",
    "GroupExpressionList",
    "GroupExpression",
)


@pytest.fixture(scope="module")
def dialog_text() -> str:
    assert DIALOG_PATH.is_file(), f"missing dialog definition: {DIALOG_PATH}"
    return DIALOG_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dialog_root(dialog_text: str) -> ET.Element:
    return ET.fromstring(dialog_text)


def test_dialog_is_well_formed_xml(dialog_root: ET.Element):
    assert dialog_root.tag == "Dialog"
    assert dialog_root.get("type") == "uicomp"


def test_dialog_has_a_readable_title(dialog_root: ET.Element):
    title = dialog_root.get("title") or ""
    assert "NX Skill" in title, f"dialog title looks unfinished: {title!r}"


def test_exactly_one_group_container(dialog_root: ET.Element):
    groups = [e for e in dialog_root if e.tag == "item" and e.get("class") == "UGS::UICOMP_group"]
    assert len(groups) == 1, "the dialog must contain exactly one group container"


def _container(dialog_root: ET.Element) -> ET.Element:
    group = next(e for e in dialog_root if e.tag == "item" and e.get("class") == "UGS::UICOMP_group")
    return next(
        el
        for el in group.iter("PropertyList")
        if el.get("id") == "ContainerItems" and el.get("class") == "UGS::UI::Comp::Container"
    )


def test_the_expected_blocks_are_present_with_the_right_types(dialog_root: ET.Element):
    found = {c.get("id"): c.get("class") for c in _container(dialog_root) if c.tag == "Property"}
    assert found == EXPECTED_BLOCKS


def test_every_block_id_agrees_with_its_blockid_property(dialog_root: ET.Element):
    """Block Styler carries the id twice; a mismatch makes the block unreachable."""
    for block in _container(dialog_root):
        if block.tag != "Property":
            continue
        declared = [p.get("value") for p in block.iter("Property") if p.get("sname") == "BlockID"]
        assert declared == [block.get("id")], f"{block.get('id')} declares BlockID {declared}"


def test_no_vendor_sample_ids_survived_the_clone(dialog_text: str):
    leaked = [name for name in STALE_IDS if name in dialog_text]
    assert leaked == [], f"dialog still references vendor sample ids: {leaked}"


def test_every_button_has_a_label(dialog_root: ET.Element):
    for block in _container(dialog_root):
        if block.tag != "Property" or block.get("class") != "UICOMP_button":
            continue
        labels = [p.get("value") for p in block.iter("Property") if p.get("sname") == "Label"]
        assert labels and labels[0], f"button {block.get('id')} has no label"


def test_the_step_list_is_tall_enough_to_be_useful(dialog_root: ET.Element):
    block = next(c for c in _container(dialog_root) if c.get("id") == "step_list")
    height = next(p.get("value") for p in block.iter("Property") if p.get("sname") == "Height")
    assert int(height) >= 8, "a review list showing fewer than 8 steps is not useful"


def test_the_step_list_cannot_be_edited_by_the_user(dialog_root: ET.Element):
    """The list mirrors the plan file; the user must not add or delete rows in it."""
    block = next(c for c in _container(dialog_root) if c.get("id") == "step_list")
    flags = {p.get("sname"): p.get("value") for p in block.iter("Property") if p.get("sname")}
    assert flags["ShowAddButton"] == "False"
    assert flags["ShowDeleteButton"] == "False"
    assert flags["ShowMoveUpDownButtons"] == "False"


def test_the_dialog_uses_close_not_ok_apply(dialog_root: ET.Element):
    """It is a control panel, not a form: OK/Apply would imply uncommitted edits."""
    navigation = None
    for prop_list in dialog_root.iter("PropertyList"):
        for prop in prop_list:
            if prop.tag == "Property" and prop.get("sname") == "Navigation Style":
                navigation = prop
    assert navigation is not None, "the dialog has no navigation style"
    choices = {option.get("value"): option.get("name") for option in navigation}
    assert choices.get(navigation.get("selected")) == "Close"


def test_the_dialog_file_is_small_enough_to_review():
    """A guard against accidentally committing an entire vendor sample."""
    assert DIALOG_PATH.stat().st_size < 200_000
