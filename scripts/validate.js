#!/usr/bin/env node
/**
 * Agentic STLC — environment validation script.
 * Checks Python version, required CLIs, and env vars.
 */
"use strict";

const { spawnSync } = require("child_process");

let allOk = true;

function check(label, ok, detail) {
  const icon = ok ? "[OK]     " : "[MISSING]";
  console.log(`  ${icon} ${label}${detail ? ": " + detail : ""}`);
  if (!ok) allOk = false;
}

function which(cmd) {
  const r = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], { encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim().split("\n")[0] : null;
}

function pythonVersion() {
  for (const cmd of ["python3", "python"]) {
    const r = spawnSync(cmd, ["-c", "import sys; print(sys.version)"], { encoding: "utf8" });
    if (r.status === 0) {
      const ver = r.stdout.trim();
      const m = ver.match(/(\d+)\.(\d+)/);
      if (m && (parseInt(m[1]) > 3 || (parseInt(m[1]) === 3 && parseInt(m[2]) >= 11))) {
        return { ok: true, cmd, version: ver.split(" ")[0] };
      }
      return { ok: false, cmd, version: ver.split(" ")[0] };
    }
  }
  return { ok: false };
}

console.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
console.log("  Agentic STLC — environment validation");
console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

console.log("Tools:");
const py = pythonVersion();
check("python 3.11+", py.ok, py.version || "not found");

const node = process.version;
const nodeOk = parseInt(node.slice(1)) >= 18;
check("node 18+", nodeOk, node);

const kane = which("kane-cli");
check("kane-cli", !!kane, kane || "not found — run: npm install -g @testmuai/kane-cli");

const git = which("git");
check("git", !!git, git || "not found");

const he = which("hyperexecute") || which("hyperexecute.exe");
check("hyperexecute", !!he, he || "not found — download from lambdatest.com/support/docs/hyperexecute-cli");

console.log("\nEnvironment variables:");
const envVars = [
  ["LT_USERNAME",     "LambdaTest username"],
  ["LT_ACCESS_KEY",   "LambdaTest access key"],
];
for (const [name, desc] of envVars) {
  const val = process.env[name];
  check(name, !!val, val ? "(set)" : `not set — ${desc}`);
}

console.log("\nConfig file:");
const fs = require("fs");
const configExists = fs.existsSync("agentic-stlc.config.yaml");
check("agentic-stlc.config.yaml", configExists,
  configExists ? "found" : "not found — run: agentic-stlc init");

console.log(`\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
if (allOk) {
  console.log("  Result: PASS — environment is ready");
} else {
  console.log("  Result: FAIL — fix the items marked [MISSING] above");
}
console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");

process.exit(allOk ? 0 : 1);
