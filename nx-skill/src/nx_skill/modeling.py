"""Modelling semantics: intent routing, plan shape, and image-driven rules.

This module carries the part of the original plugin that is actually *knowledge*
rather than plumbing: how to route a request to the right NX sub-system, what a
good part history looks like, and how to interpret an orthographic drawing. It is
deliberately free of NX session state so it can be unit-tested without NX and
consumed by any host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

#: Prompts that imply the model must be derived from a picture or a drawing.
VISUAL_KEYWORDS: tuple[str, ...] = (
    "图片", "图像", "照片", "识图", "图纸", "工程图", "机械图",
    "三视图", "主视图", "俯视图", "左视图", "右视图", "正视图", "侧视图",
    "剖视图", "投影视图", "中心线", "隐藏线",
    "image", "photo", "picture", "drawing", "blueprint", "orthographic",
    "three-view", "3-view", "front view", "top view", "side view",
    "section view", "centerline", "hidden line",
)

MODELING_KEYWORDS: tuple[str, ...] = (
    "建模", "模型", "零件", "实体", "特征", "草图", "拉伸", "旋转", "扫掠",
    "放样", "倒角", "圆角", "孔", "凸台", "壳", "曲面", "装配",
    "modeling", "model", "part", "solid", "feature", "sketch", "extrude",
    "revolve", "sweep", "loft", "block", "hole", "chamfer", "fillet",
    "boss", "shell", "assembly",
) + VISUAL_KEYWORDS

SIMULATION_KEYWORDS: tuple[str, ...] = (
    "仿真", "有限元", "有限元素", "分析", "网格", "求解", "载荷", "边界条件",
    "约束", "应力", "应变", "位移", "模态", "频率", "热分析", "结构分析", "后处理",
    "cae", "fea", "simulation", "simulate", "analysis", "mesh", "solver",
    "load", "boundary condition", "stress", "strain", "displacement",
    "modal", "thermal", "post-processing",
)

#: Modelling is checked first so an ambiguous prompt like "分析这个零件的强度"
#: still routes to the CAD side when a geometry verb is present.
_ROUTES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("modeling", "Modeling / 建模", MODELING_KEYWORDS),
    ("simulation", "Simulation / 仿真", SIMULATION_KEYWORDS),
)

_ROUTE_DETAIL: dict[str, dict[str, Any]] = {
    "modeling": {
        "nxApplication": "UG_APP_MODELING",
        "primaryModules": ("NXOpen", "NXOpen.Features"),
        "optionalModules": ("NXOpen.Assemblies", "NXOpen.GeometricUtilities", "NXOpen.Drawings"),
        "historyMode": "parameterized_feature_tree",
        "guidance": (
            "Switch to UG_APP_MODELING and build editable, history-preserving features. Prefer sketches, "
            "datum objects and expressions over a single final body, and give every committed object an "
            "ordered navigator name."
        ),
    },
    "simulation": {
        "nxApplication": "CAE workflow",
        "primaryModules": ("NXOpen", "NXOpen.CAE"),
        "optionalModules": ("NXOpen.SIM", "NXOpen.Fields"),
        "historyMode": "cae_simulation_tree",
        "guidance": (
            "Verify the CAE modules exist in this installation before creating meshes, loads, constraints "
            "or solutions; CAE availability differs per licence and per installation option."
        ),
    },
}


def _fold(text: object) -> str:
    return str(text or "").casefold()


def is_visual_prompt(prompt: object) -> bool:
    """Whether a prompt asks for a model derived from a picture or drawing."""
    folded = _fold(prompt)
    return any(keyword.casefold() in folded for keyword in VISUAL_KEYWORDS)


@dataclass(frozen=True)
class Intent:
    """The routing decision for one user request."""

    name: str
    display_name: str
    score: int
    matched: tuple[str, ...] = ()
    nx_application: str = ""
    primary_modules: tuple[str, ...] = ()
    optional_modules: tuple[str, ...] = ()
    guidance: str = ""
    visual: bool = False
    alternatives: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.name,
            "displayName": self.display_name,
            "score": self.score,
            "matchedKeywords": list(self.matched),
            "nxApplication": self.nx_application,
            "primaryModules": list(self.primary_modules),
            "optionalModules": list(self.optional_modules),
            "guidance": self.guidance,
            "visualReference": self.visual,
            "otherRoutes": [{"route": name, "score": score} for name, score in self.alternatives],
        }


def route_intent(prompt: object) -> Intent:
    """Pick the NX sub-system a request belongs to, with an auditable score.

    Scoring counts distinct keyword hits and breaks ties by declaration order, so
    the result is deterministic and a caller can see *why* a route won instead of
    trusting an opaque classification.
    """
    folded = _fold(prompt)
    ranked: list[tuple[int, str, str, list[str]]] = []
    for name, display, keywords in _ROUTES:
        matched = [kw for kw in keywords if kw.casefold() in folded]
        ranked.append((len(matched), name, display, matched))

    ranked.sort(key=lambda item: item[0], reverse=True)
    score, name, display, matched = ranked[0]
    detail = _ROUTE_DETAIL[name]

    if score == 0:
        # Nothing matched: default to modelling, which is the overwhelmingly
        # common request, but say so explicitly rather than pretending confidence.
        name, display, detail = "modeling", "Modeling / 建模", _ROUTE_DETAIL["modeling"]

    return Intent(
        name=name,
        display_name=display,
        score=score,
        matched=tuple(matched[:12]),
        nx_application=detail["nxApplication"],
        primary_modules=tuple(detail["primaryModules"]),
        optional_modules=tuple(detail["optionalModules"]),
        guidance=detail["guidance"],
        visual=is_visual_prompt(prompt),
        alternatives=tuple((other_name, other_score) for other_score, other_name, _, _ in ranked[1:]),
    )


# ---------------------------------------------------------------------------
# History-preserving modelling policy
# ---------------------------------------------------------------------------

PART_NAVIGATOR_POLICY: dict[str, Any] = {
    "mustUse": [
        "NXOpen expressions for every dimension that may need to change",
        "Datum planes/axes or a coordinate system when they clarify design intent",
        "Sketches for profile-driven geometry whenever practical",
        "NXOpen.Features builders (Extrude, Revolve, Hole, EdgeBlend, Chamfer, Shell, Pattern, Boolean)",
        "session.SetUndoMark(name) around each human-sized operation",
        "SetName(...) on every sketch, datum and committed feature",
    ],
    "avoid": [
        "Emitting only a final faceted or dumb BRep body",
        "Leaving default feature names in the Part Navigator",
        "One oversized journal stage for a complex part",
        "Deleting construction geometry that explains the design intent",
    ],
}


def plan_template(
    prompt: object = "",
    *,
    part_name: str = "NX_Model",
    units: str = "Millimeters",
    include_visual_policy: bool | None = None,
) -> dict[str, Any]:
    """Return the schema an ordered, editable modelling plan must follow."""
    safe_name = (str(part_name).strip() or "NX_Model").replace(" ", "_")
    show_visual = is_visual_prompt(prompt) if include_visual_policy is None else include_visual_policy

    plan: dict[str, Any] = {
        "mode": "history_preserving_parameterized_modeling",
        "prompt": str(prompt or ""),
        "partName": safe_name,
        "goal": (
            "Produce editable NX feature history so the Part Navigator reads as a clear sequence of "
            "modelling steps rather than one opaque final body."
        ),
        "beforeRunning": [
            "Write the ordered plan before executing any journal.",
            "Split the part into stages: reference geometry, base body, primary cuts/additions, patterns, finishing, validation.",
            "Keep every step small enough that its failure is diagnosable on its own.",
        ],
        "namingConvention": {
            "format": "NN_Short_Action_Object",
            "examples": [
                f"01_{safe_name}_Datum_CSYS",
                "02_Base_Profile_Sketch",
                "03_Base_Extrude",
                "04_Main_Bore_RevolveCut",
                "05_Mounting_Holes_Pattern",
                "06_Edge_Fillets",
                "07_Final_Check",
            ],
        },
        "partNavigatorPolicy": PART_NAVIGATOR_POLICY,
        "planSchema": {
            "part_name": safe_name,
            "units": units,
            "design_intent": "What the model represents and which dimensions stay editable.",
            "expressions": [
                {"name": "base_length", "formula": "100", "unit": "mm", "purpose": "drives the base feature"}
            ],
            "steps": [
                {
                    "id": "01",
                    "navigator_name": "01_Base_Profile_Sketch",
                    "operation": "sketch",
                    "nxopen_modules": ["NXOpen"],
                    "inputs": ["datum plane", "expressions"],
                    "creates": ["named sketch profile"],
                    "validation": "Sketch exists and is constrained enough for the next feature.",
                },
                {
                    "id": "02",
                    "navigator_name": "02_Base_Extrude",
                    "operation": "feature_builder",
                    "nxopen_modules": ["NXOpen", "NXOpen.Features"],
                    "inputs": ["01_Base_Profile_Sketch"],
                    "creates": ["solid feature"],
                    "validation": "Feature appears in the Part Navigator and the body matches the intended size.",
                },
            ],
        },
    }
    if show_visual:
        plan["visualModelingPolicy"] = visual_spec(prompt)
    return plan


# ---------------------------------------------------------------------------
# Orthographic / image-driven modelling
# ---------------------------------------------------------------------------


def visual_spec(
    prompt: object = "",
    *,
    projection_system: str = "infer",
    view_layout: str = "",
    units: str = "mm",
) -> dict[str, Any]:
    """Rules for building a model from a picture, blueprint or three-view drawing."""
    return {
        "mode": "orthographic_reference_modeling",
        "prompt": str(prompt or ""),
        "units": (units or "mm").strip() or "mm",
        "projectionSystem": {
            "requested": (projection_system or "infer").strip() or "infer",
            "rules": [
                "Follow an explicit projection symbol or written view labels first.",
                "If labels conflict with layout, trust the labels and record the conflict as an assumption.",
                "First-angle (ISO/GB): the top view usually sits below the front view and a left-side view may appear on the right.",
                "Third-angle: the top view usually sits above the front view and the right-side view appears on the right.",
                "With no symbol or labels, infer the least-mirrored reading of the visible features and any symmetry.",
            ],
            "viewLayoutHint": view_layout or "",
        },
        "defaultAssumptions": [
            "Do not stop for confirmation before a first modelling pass when the image already gives enough shape information.",
            "Use millimetres unless the drawing states otherwise.",
            "Use labelled dimensions exactly; where a dimension is missing, preserve the visual proportion with an editable expression.",
            "Treat centrelines, symmetry marks, hidden lines and section hatching as real design evidence.",
            "Ask the user only when projection handedness, scale, or hidden internal geometry would materially change the part.",
        ],
        "viewExtractionChecklist": [
            "Identify front/main, top and side views from labels, placement or projection convention.",
            "Extract the front silhouette, the top footprint, the side depth profile, hole centres, axes, slots, bosses, ribs, rounds, chamfers and cut-outs.",
            "Separate visible edges, hidden edges, centrelines, section edges, cosmetic lines and dimension leaders.",
            "Map each major feature to at least two views wherever possible before creating the NX feature.",
            "Record unresolved features as named assumptions instead of silently inventing final geometry.",
        ],
        "nxModelingRules": [
            "Create named reference geometry for the views, e.g. 01_Reference_Front_View, 02_Reference_Top_View, 03_Reference_Side_View.",
            "Start from the dominant front profile, then constrain depth and footprint from the top and side views.",
            "Create bosses, holes, slots, ribs, pockets, shells, chamfers and fillets as separate named editable features.",
            "Drive important sizes and inferred proportions with NX expressions so later corrections stay cheap.",
            "Name features with the view evidence, e.g. 04_Top_View_Slot_Cut.",
        ],
        "validationChecklist": [
            "The front silhouette matches the source, including hole and cut-out positions.",
            "The top footprint and depth transitions match the source.",
            "The side height/depth profile matches the source.",
            "Round, chamfer, fillet, shell and wall-thickness assumptions are named and visually plausible.",
            "Hidden-line features produce the expected internal or rear geometry when the model is reoriented.",
            "The final work view is fitted and the assumptions used are reported.",
        ],
        "workflow": [
            "Route the request once with the original prompt so the visual policy is attached.",
            "Create or reuse a modelling part, asking only when an existing file would be overwritten.",
            "Run staged steps: reference setup, base body, primary cuts/additions, secondary details, finishing, validation.",
            "After each stage, re-check the model against the front/top/side constraints before continuing.",
        ],
    }
