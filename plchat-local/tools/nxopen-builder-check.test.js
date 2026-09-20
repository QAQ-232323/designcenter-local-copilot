"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { checkBuilderBooleanMembers } = require("./nxopen-builder-check");

const index = new Set(fs.readFileSync(path.join(__dirname, "..", "cache", "nxopen-names.txt"), "utf8")
  .split(/\r?\n/).map(s => s.trim()).filter(Boolean));

test("rejects the CylinderBuilder.BooleanOperation used by the failed journal", () => {
  const script = "builder = work_part.Features.CreateCylinderBuilder(None)\n" +
    "builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create";
  const result = checkBuilderBooleanMembers(script, index);
  assert.equal(result.ok, false);
  assert.ok(result.issues.some(issue => issue.member === "builder.BooleanOperation" &&
    issue.suggestion === "builder.BooleanOption"));
});

test("accepts the installed release's BooleanOption on CylinderBuilder", () => {
  const script = "b = part.Features.CreateCylinderBuilder(None)\nb.BooleanOption.Type = C.Create";
  assert.equal(checkBuilderBooleanMembers(script, index).ok, true);
});

test("uses the builder type instead of banning BooleanOperation globally", () => {
  const script = "b = part.Features.CreateExtrudeBuilder(None)\nb.BooleanOperation.Type = C.Create";
  assert.equal(checkBuilderBooleanMembers(script, index).ok, true);
});

test("suggests SetTargetBodies for the unsupported TargetBodies property", () => {
  const script = "b = part.Features.CreateCylinderBuilder(None)\nb.BooleanOption.TargetBodies = bodies";
  const result = checkBuilderBooleanMembers(script, index);
  assert.equal(result.ok, false);
  assert.equal(result.issues[0].suggestion, "b.BooleanOption.SetTargetBodies(bodies)");
});
