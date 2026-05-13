#!/usr/bin/env node
/**
 * Post-install script for the agentic-stlc npm package.
 * Checks Python 3.11+ is available and prints a quick-start guide.
 */
"use strict";

const { spawnSync } = require("child_process");

function checkPython() {
  for (const cmd of ["python3", "python"]) {
    const r = spawnSync(cmd, ["-c", "import sys; print(sys.version)"], { encoding: "utf8" });
    if (r.status === 0) {
      const ver = r.stdout.trim();
      const match = ver.match(/(\d+)\.(\d+)/);
      if (match && (parseInt(match[1]) > 3 || (parseInt(match[1]) === 3 && parseInt(match[2]) >= 11))) {
        return { ok: true, cmd, version: ver };
      }
    }
  }
  return { ok: false };
}

const python = checkPython();

console.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
console.log("  Agentic STLC Platform — installed");
console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

if (python.ok) {
  console.log(`  ✅  Python: ${python.version.split(" ")[0]} (${python.cmd})`);
} else {
  console.log("  ❌  Python 3.11+ not found — required for the pipeline");
  console.log("      Install from: https://www.python.org/downloads/");
}

console.log("\n  Quick start:");
console.log("    agentic-stlc init           # scaffold config");
console.log("    agentic-stlc validate       # check environment");
console.log("    agentic-stlc run            # run full pipeline");
console.log("    agentic-stlc status         # show latest results");
console.log("\n  Docs: https://github.com/lambdapro/agentic-stlc-kane-hyperexecute");
console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
