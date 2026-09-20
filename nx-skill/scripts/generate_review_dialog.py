#!/usr/bin/env python3
"""Generate nx_review_executor.dlx by reusing Siemens' own Block Styler blocks.

A Block Styler dialog is defined by a \`.dlx\` file, which is normally produced by
the Block UI Styler editor inside NX. This package has to ship one, and a
hand-written one is a liability: each block carries a couple of dozen mandatory
\`<Property>\` entries with class ids, masks and internal names that cannot be
guessed.

So this script does not author a dialog from scratch. It takes a **vendor-generated
sample dialog as the document skeleton** and **clones whole block definitions**
out of vendor samples, renaming only their block ids. Everything structural --
the \`<Dialog>\` element, the group container, the attachment properties, the
dialog-level property list -- comes from Siemens and is therefore known-valid.

Run it against any NX installation:

    python scripts/generate_review_dialog.py --nx-root "D:\\Program Files\\Siemens\\NX 2512"

With no argument it uses this package's own discovery to find NX.
"""

from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

OUTPUT = REPO_ROOT / "nx_runtime" / "application" / "nx_review_executor.dlx"

#: The vendor sample used as the document skeleton (dialog + group + properties).
SKELETON = "C++/BlockStyler/EditExpression/EditExpression.dlx"
#: Where each block type is copied from, as (relative sample path, block id).
BLOCK_SOURCES = {
    "list_box": ("C++/BlockStyler/EditExpression/EditExpression.dlx", "ExpressionList"),
    "button": ("C++/BlockStyler/EditExpression/EditExpression.dlx", "ButtonGetExpressions"),
    "label": ("DotNet/CAE/CampbellCsvToAfu/CampbellCsvToAfu.dlx", "label0"),
}

#: The dialog's blocks, in display order.
BLOCKS = [
    ("label", "status_label", {"Label": "Loading plan..."}),
    ("list_box", "step_list", {"Label": "Steps / 步骤", "Height": "14"}),
    ("button", "run_next", {"Label": "Run Next Step / 执行下一步"}),
    ("button", "undo_last", {"Label": "Undo Last Step / 撤销上一步"}),
    ("button", "run_auto", {"Label": "Run All Automatic / 连续执行自动步骤"}),
    ("button", "refresh", {"Label": "Reload Plan / 重新载入计划"}),
]

DIALOG_TITLE = "NX Skill Review"

#: The skeleton has no Navigation Style property, so it is cloned from a sample
#: that does. Without it the dialog would present OK/Apply buttons, which implies
#: an uncommitted edit -- this dialog is a control panel, so it should have Close.
NAVIGATION_SOURCE = "Java/BlockStyler/ChangeFaceColor/ChangeFaceColor.dlx"
GROUP_ID = "group0"
GROUP_LABEL = "Review Plan / 复核计划"


def find_block(root: ET.Element, cls: str | None, block_id: str | None = None) -> ET.Element:
    for el in root.iter("Property"):
        if cls is not None and el.get("class") != cls:
            continue
        if block_id is not None and el.get("id") != block_id:
            continue
        return el
    raise LookupError(f"no <Property class={cls!r} id={block_id!r}> found")


def find_by_sname(root: ET.Element, sname: str) -> ET.Element:
    for el in root.iter("Property"):
        if el.get("sname") == sname:
            return el
    raise LookupError(f"no <Property sname={sname!r}> found")


def set_property(block: ET.Element, sname: str, value: str) -> bool:
    """Set the value of the first property with this internal name."""
    for el in block.iter("Property"):
        if el.get("sname") == sname:
            el.set("value", value)
            return True
    return False


def rename_block(block: ET.Element, old_id: str, new_id: str) -> None:
    """Rewrite every occurrence of the block id: element ids, names and BlockID."""
    for node in block.iter():
        for key, value in list(node.attrib.items()):
            if value == old_id:
                node.set(key, new_id)


def clone_block(
    sample_root: ET.Element,
    cls: str,
    source_id: str,
    new_id: str,
    overrides: dict[str, str],
) -> ET.Element:
    source = find_block(sample_root, cls, source_id)
    block = copy.deepcopy(source)
    rename_block(block, source_id, new_id)

    applied = set()
    for sname, value in overrides.items():
        if set_property(block, sname, value):
            applied.add(sname)
    missing = set(overrides) - applied
    if missing:
        # Loud rather than silent: a label that never got set is a bug the user
        # would otherwise only discover by opening the dialog in NX.
        raise SystemExit(f"block {new_id!r} ({cls}) has no property named {sorted(missing)}")
    return block


def build(nx_root: Path) -> ET.ElementTree:
    samples = nx_root / "UGOPEN" / "SampleNXOpenApplications"
    if not samples.is_dir():
        raise SystemExit(
            f"Block Styler samples not found under {samples}.\n"
            "Point --nx-root at an NX installation that includes UGOPEN/SampleNXOpenApplications."
        )

    tree = ET.parse(str(samples / SKELETON))
    dialog = tree.getroot()
    dialog.set("title", DIALOG_TITLE)
    dialog.set("name", "nx_review_executor")

    # Keep exactly one group container and drop the sample's other groups.
    groups = [el for el in dialog if el.tag == "item" and el.get("class") == "UGS::UICOMP_group"]
    if not groups:
        raise SystemExit("the skeleton dialog contains no group container")
    keep, drop = groups[0], groups[1:]
    for element in drop:
        dialog.remove(element)

    # The kept group is still carrying the vendor sample's id; rename it so the
    # document contains no reference to the sample it was cloned from.
    rename_block(keep, keep.get("id", ""), GROUP_ID)
    if not set_property(keep, "Label", GROUP_LABEL):
        raise SystemExit("the group container has no Label property")

    containers = [
        el for el in keep.iter("PropertyList")
        if el.get("id") == "ContainerItems" and el.get("class") == "UGS::UI::Comp::Container"
    ]
    if not containers:
        raise SystemExit("the skeleton group has no ContainerItems list")
    container = containers[0]
    for child in list(container):
        container.remove(child)

    cache: dict[str, ET.Element] = {}
    for cls, new_id, overrides in BLOCKS:
        rel, source_id = BLOCK_SOURCES[cls]
        if rel not in cache:
            cache[rel] = ET.parse(str(samples / rel)).getroot()
        block = clone_block(cache[rel], _CLASS_OF[cls], source_id, new_id, overrides)
        container.append(block)

    # The review dialog is a control panel, not a form: give it a Close button
    # rather than OK/Apply so nothing implies an uncommitted edit. The skeleton
    # lacks the property entirely, so it is cloned from a sample that has it.
    navigation = copy.deepcopy(
        find_by_sname(ET.parse(str(samples / NAVIGATION_SOURCE)).getroot(), "Navigation Style")
    )
    close_values = [option.get("value") for option in navigation if option.get("name") == "Close"]
    if not close_values:
        raise SystemExit("the navigation style property has no 'Close' option")
    navigation.set("selected", close_values[0])
    for element in dialog:
        if element.tag == "PropertyList":
            element.append(navigation)
            break
    else:
        raise SystemExit("the dialog has no top-level PropertyList to hold the navigation style")

    return tree


_CLASS_OF = {
    "list_box": "UICOMP_list_box",
    "button": "UICOMP_button",
    "label": "UICOMP_label",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nx-root", help="NX installation root (contains UGOPEN/)")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()

    if args.nx_root:
        nx_root = Path(args.nx_root)
    else:
        from nx_skill.config import Settings
        from nx_skill.discovery import discover

        nx_root = discover(settings=Settings.from_env()).root

    tree = build(nx_root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(str(output), encoding="UTF-8", xml_declaration=True)

    blocks = [
        (el.get("class"), el.get("id"))
        for el in tree.getroot().iter("Property")
        if el.get("class") in _CLASS_OF.values()
    ]
    print(f"wrote {output} ({output.stat().st_size} bytes)")
    for cls, block_id in blocks:
        print(f"  {cls:18} {block_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())