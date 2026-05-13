#!/usr/bin/env node
/**
 * Agentic STLC CLI — Node.js entry point.
 *
 * Delegates to the Python CLI (`cli/main.py`) via a subprocess call.
 * This allows the package to be installed with `npm install -g agentic-stlc`
 * while keeping the core implementation in Python.
 *
 * Usage:
 *   agentic-stlc run --repo https://github.com/org/app --branch main
 *   agentic-stlc analyze --requirements requirements/search.txt
 *   agentic-stlc status
 *   agentic-stlc init
 *   agentic-stlc validate
 */
"use strict";

const { spawnSync } = require("child_process");
const path = require("path");
const fs   = require("fs");

const args = process.argv.slice(2);

// Detect Python command (python3 preferred on Linux/Mac, python on Windows)
function findPython() {
  for (const cmd of ["python3", "python"]) {
    const result = spawnSync(cmd, ["--version"], { encoding: "utf8" });
    if (result.status === 0 && result.stdout.includes("Python 3")) {
      return cmd;
    }
  }
  return null;
}

const python = findPython();
if (!python) {
  console.error("ERROR: Python 3.11+ is required but not found on PATH.");
  console.error("Install Python from https://www.python.org/downloads/");
  process.exit(1);
}

// Find cli/main.py — first look in the package root, then CWD
const candidates = [
  path.join(__dirname, "..", "cli", "main.py"),
  path.join(process.cwd(), "cli", "main.py"),
];

const cliScript = candidates.find(fs.existsSync);
if (!cliScript) {
  console.error("ERROR: cli/main.py not found. Is agentic-stlc installed correctly?");
  process.exit(1);
}

const result = spawnSync(python, [cliScript, ...args], {
  stdio:  "inherit",
  cwd:    process.cwd(),
  env:    process.env,
});

process.exit(result.status ?? 1);
