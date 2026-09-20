"use strict";

/** Check boolean member names against the API index for the installed NX release.
 * The main NXOpen-name check cannot see properties accessed through local variables.
 */
function checkBuilderBooleanMembers(code, index) {
  if (!index || !index.size) return { ok: true, issues: [], note: "NXOpen index unavailable" };
  const builders = new Map();
  const issues = [];
  const lines = String(code).split(/\r?\n/);
  for (let lineNumber = 0; lineNumber < lines.length; lineNumber++) {
    const line = lines[lineNumber];
    const assigned = line.match(/\b([A-Za-z_]\w*)\s*=\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\.Features\.Create([A-Za-z_]\w*Builder)\s*\(/);
    if (assigned) {
      const type = "NXOpen.Features." + assigned[2];
      if (index.has(type)) builders.set(assigned[1], type);
    }
    const access = /\b([A-Za-z_]\w*)\.(BooleanOption|BooleanOperation)\b/g;
    let match;
    while ((match = access.exec(line)) !== null) {
      const type = builders.get(match[1]);
      if (!type) continue;
      const member = match[2];
      const alternative = member === "BooleanOption" ? "BooleanOperation" : "BooleanOption";
      if (!index.has(type + "." + member) && index.has(type + "." + alternative)) {
        issues.push({ line: lineNumber + 1, member: match[1] + "." + member,
          type, suggestion: match[1] + "." + alternative });
      }
      if (line.slice(match.index + match[0].length).startsWith(".TargetBodies") &&
          !index.has("NXOpen.GeometricUtilities.BooleanOperation.TargetBodies") &&
          index.has("NXOpen.GeometricUtilities.BooleanOperation.SetTargetBodies")) {
        issues.push({ line: lineNumber + 1, member: match[1] + "." + member + ".TargetBodies",
          type, suggestion: match[1] + "." + member + ".SetTargetBodies(bodies)" });
      }
    }
  }
  return { ok: issues.length === 0, issues };
}

module.exports = { checkBuilderBooleanMembers };
