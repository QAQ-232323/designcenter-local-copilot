"""Search the API reference that ships *inside* the NX installation.

Why this exists: the historical public NXOpen reference host is not a reliable
research target any more -- every path under
`docs.plm.automation.siemens.com/data_services/resources/nx/<release>/...`
now redirects to an authenticated customer centre, and the live portal is behind
a login. Meanwhile the install on the machine already contains a complete,
release-exact reference:

* `NXBIN/managed/*.xml` -- .NET XML documentation for every managed assembly
  (tens of megabytes; each member carries its signature, summary, and the
  release that introduced it, e.g. "Created in NX2206.0.0").
* `UGOPEN/pythonStubs/NXOpen/**` -- Python type stubs for the same API surface.
* `UGOPEN/SampleNXOpenApplications/**` -- vendor sample code.
* `UGOPEN/exphdrs` -- C/C++ headers.

Querying these gives an answer that is exactly right for the installed release,
works offline, and never guesses. This module streams the XML rather than loading
it, so a search over a 59 MB file stays cheap and bounded.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .contracts import DocsUnavailable
from .discovery import NxInstall

#: NX documentation member prefixes.
KIND_PREFIXES: dict[str, str] = {
    "N": "namespace",
    "T": "type",
    "M": "method",
    "P": "property",
    "F": "field",
    "E": "event",
}
PREFIX_KINDS: dict[str, str] = {v: k for k, v in KIND_PREFIXES.items()}

_RELEASE_NOTE = re.compile(r"Created in (?:NX|UG)?\s*([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE)
_WS = re.compile(r"\s+")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text).strip()


def _section_text(element: ElementTree.Element, tag: str) -> str:
    """Flatten one documentation section to plain text.

    `ElementTree.findtext` returns only the text *directly* inside the element and
    silently drops everything after a nested tag, which would truncate summaries
    such as `Gets the singleton for <see cref="Session"/>` at the word "for".
    `itertext()` walks the whole subtree, so nested `<see>`, `<para>` and
    `<paramref>` content is preserved.
    """
    node = element.find(tag)
    if node is None:
        return ""
    return _clean(_render(node))


def _render(node: ElementTree.Element) -> str:
    """Flatten a node, resolving reference elements that carry no text.

    Vendor documentation writes cross references both ways:
    `<see cref="T:NXOpen.Session">NXOpen.Session</see>` and the empty
    `<see cref="T:NXOpen.Session"/>`. The second form contributes no text at all,
    which would leave a sentence reading "Gets the singleton for ." -- so the
    cref is turned back into a readable name.
    """
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        inner = _render(child)
        if not inner:
            cref = child.get("cref") or ""
            if cref:
                # "T:NXOpen.Session" -> "NXOpen.Session"
                inner = cref[2:] if len(cref) > 2 and cref[1] == ":" else cref
        parts.append(inner)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


@dataclass
class ApiMember:
    """One documented API member from the shipped .NET XML reference."""

    name: str  # e.g. "M:NXOpen.Session.GetSession"
    assembly: str  # e.g. "NXOpen"
    summary: str = ""
    remarks: str = ""
    returns: str = ""
    params: dict[str, str] = field(default_factory=dict)
    created_in: str | None = None

    @property
    def kind(self) -> str:
        return KIND_PREFIXES.get(self.name[:1], "unknown")

    @property
    def qualified(self) -> str:
        return self.name[2:] if len(self.name) > 2 and self.name[1] == ":" else self.name

    @property
    def _base(self) -> str:
        r"""The qualified name without its parameter list.

        Splitting on the last dot is wrong for real signatures: the parameter list
        of \`SetListItems(System.String[])\` itself contains dots, so a naive
        \`rsplit('.', 1)\` reports the member as \`String[])\`. Trimming the parameter
        list first keeps type and member names correct.
        """
        return self.qualified.split("(", 1)[0]

    @property
    def declaring_type(self) -> str:
        parts = self._base.rsplit(".", 1)
        return parts[0] if len(parts) == 2 else ""

    @property
    def member(self) -> str:
        declaring = self.declaring_type
        if not declaring:
            return self.qualified
        return self.qualified[len(declaring) + 1 :]

    def to_dict(self, *, full: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.qualified,
            "kind": self.kind,
            "assembly": self.assembly,
            "summary": self.summary,
            "createdIn": self.created_in,
        }
        if full:
            payload["signature"] = self.member
            payload["declaringType"] = self.declaring_type
            payload["params"] = self.params
            payload["returns"] = self.returns
            payload["remarks"] = self.remarks[:2000]
        return payload


class ApiDocs:
    """Read-only view over the documentation bundled with an NX install."""

    def __init__(self, install: NxInstall) -> None:
        self.install = install

    # -- availability -----------------------------------------------------
    @property
    def xml_files(self) -> tuple[Path, ...]:
        return self.install.api_xml_docs

    @property
    def stubs_root(self) -> Path | None:
        return self.install.python_stubs

    @property
    def examples_root(self) -> Path | None:
        return self.install.examples

    def available(self) -> bool:
        return bool(self.xml_files) or self.stubs_root is not None

    def require(self) -> None:
        if not self.available():
            raise DocsUnavailable(
                "This NX installation ships no readable API documentation.",
                suggestion=(
                    "Point NX_SKILL_NX_ROOT at a full NX installation; the reference lives in "
                    "NXBIN/managed/*.xml and UGOPEN/pythonStubs/. Alternatively use the online "
                    "documentation, which requires a Siemens account."
                ),
                details={"root": str(self.install.root)},
            )

    def stats(self) -> dict[str, object]:
        xml_files = self.xml_files
        total = 0
        for path in xml_files:
            try:
                total += path.stat().st_size
            except OSError:
                continue
        stub_count = 0
        stubs = self.stubs_root
        if stubs is not None:
            stub_count = sum(1 for _ in stubs.rglob("*.pyi"))
        return {
            "nxRoot": str(self.install.root),
            "release": self.install.release,
            "xmlDocFiles": len(xml_files),
            "xmlBytes": total,
            "pythonStubFiles": stub_count,
            "examplesRoot": str(self.examples_root) if self.examples_root else None,
        }

    # -- XML reference ----------------------------------------------------
    def _iter_members(self, path: Path) -> Iterator[tuple[str, ElementTree.Element]]:
        """Stream `<member>` elements from one documentation file."""
        try:
            context = ElementTree.iterparse(str(path), events=("end",))
        except OSError:
            return
        try:
            for _event, element in context:
                if element.tag != "member":
                    continue
                name = element.get("name") or ""
                yield name, element
                element.clear()
        except ElementTree.ParseError:
            return

    @staticmethod
    def _parse_member(name: str, element: ElementTree.Element, assembly: str) -> ApiMember:
        summary = _section_text(element, "summary")
        remarks = _section_text(element, "remarks")
        returns = _section_text(element, "returns")
        params = {
            node.get("name", ""): _clean("".join(node.itertext()))
            for node in element.findall("param")
            if node.get("name")
        }
        release_match = _RELEASE_NOTE.search(remarks) or _RELEASE_NOTE.search(summary)
        return ApiMember(
            name=name,
            assembly=assembly,
            summary=summary,
            remarks=remarks,
            returns=returns,
            params=params,
            created_in=release_match.group(1) if release_match else None,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        kinds: Sequence[str] | None = None,
        assemblies: Sequence[str] | None = None,
        search_summary: bool = False,
        include_remarks: bool = False,
    ) -> list[ApiMember]:
        """Find documented members whose name (optionally summary) matches.

        Matching is a case-insensitive substring test, which is what an agent
        actually wants: `search("ExtrudeBuilder")` or `search("Session.GetSession")`.
        Results are capped by *limit* and the scan stops as soon as it is reached,
        so a broad query stays fast even though the corpus is ~70 MB.
        """
        self.require()
        needle = query.strip()
        if not needle:
            return []

        wanted = {k.casefold() for k in kinds} if kinds else None
        wanted_assemblies = {a.casefold() for a in assemblies} if assemblies else None
        lowered = needle.casefold()

        results: list[ApiMember] = []
        for path in self.xml_files:
            if wanted_assemblies and path.stem.casefold() not in wanted_assemblies:
                continue
            for name, element in self._iter_members(path):
                prefix = KIND_PREFIXES.get(name[:1])
                if prefix is None or (wanted and prefix not in wanted):
                    continue
                if lowered not in name.casefold():
                    if not search_summary:
                        continue
                    text = (_section_text(element, "summary") + " " + _section_text(element, "remarks")).casefold()
                    if lowered not in text:
                        continue
                results.append(self._parse_member(name, element, path.stem))
                if len(results) >= limit:
                    return results
        return results

    def member(self, qualified_name: str, *, assembly: str | None = None) -> ApiMember | None:
        """Fetch one member by its qualified name, without the kind prefix.

        `docs.member("NXOpen.Session.GetSession")` returns the documented member
        regardless of whether it is a method, property or type.
        """
        self.require()
        target = qualified_name.strip()
        if not target:
            return None
        # Members are documented under their full signature, e.g.
        # "M:NXOpen.UI.CreateDialog(System.String)". Callers naturally type the bare
        # name, so an exact match is tried first and a signature-insensitive match
        # second -- otherwise the most obvious lookup in the API silently fails.
        for path in self.xml_files:
            if assembly and path.stem.casefold() != assembly.casefold():
                continue
            for name, element in self._iter_members(path):
                if len(name) > 2 and name[1] == ":" and name[2:] == target:
                    return self._parse_member(name, element, path.stem)

        for path in self.xml_files:
            if assembly and path.stem.casefold() != assembly.casefold():
                continue
            for name, element in self._iter_members(path):
                if len(name) <= 2 or name[1] != ":":
                    continue
                qualified = name[2:]
                if qualified.split("(", 1)[0] == target:
                    return self._parse_member(name, element, path.stem)
        return None

    def type_members(self, type_name: str, *, limit: int = 200) -> list[ApiMember]:
        """List the documented members of one type, e.g. `NXOpen.Features.ExtrudeBuilder`."""
        self.require()
        prefix = (type_name.strip().rstrip(".") + ".").casefold()
        wanted = ("T:" + type_name.strip()).casefold()
        results: list[ApiMember] = []
        for path in self.xml_files:
            for name, element in self._iter_members(path):
                lowered = name.casefold()
                if lowered != wanted and not lowered.startswith(("m:" + prefix, "p:" + prefix, "f:" + prefix, "e:" + prefix)):
                    continue
                results.append(self._parse_member(name, element, path.stem))
                if len(results) >= limit:
                    return results
        return results

    # -- Python stubs and samples ----------------------------------------
    def search_stubs(self, query: str, *, limit: int = 40) -> list[dict[str, str]]:
        """Grep the shipped `NXOpen` type stubs for a symbol."""
        stubs = self.stubs_root
        if stubs is None:
            return []
        needle = query.strip().casefold()
        if not needle:
            return []

        hits: list[dict[str, str]] = []
        for path in sorted(stubs.rglob("*.pyi")):
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for number, line in enumerate(handle, start=1):
                        if needle in line.casefold():
                            hits.append(
                                {
                                    "file": str(path.relative_to(stubs)),
                                    "line": str(number),
                                    "text": line.rstrip()[:300],
                                }
                            )
                            if len(hits) >= limit:
                                return hits
            except OSError:
                continue
        return hits

    def sample_applications(self, query: str = "", *, limit: int = 40) -> list[str]:
        """List vendor sample applications, optionally filtered by name."""
        root = self.examples_root
        if root is None:
            return []
        needle = query.strip().casefold()
        found: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = str(path.relative_to(root)).replace("\\", "/")
            if needle and needle not in relative.casefold():
                continue
            found.append(relative)
            if len(found) >= limit:
                break
        return found
