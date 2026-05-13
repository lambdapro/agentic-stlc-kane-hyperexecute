#!/usr/bin/env node
/**
 * Agentic STLC — scaffold agentic-stlc.config.yaml in the current directory.
 */
"use strict";

const fs   = require("fs");
const path = require("path");

const dest = path.join(process.cwd(), "agentic-stlc.config.yaml");

if (fs.existsSync(dest)) {
  console.log(`Config already exists: ${dest}`);
  console.log("Delete it first or edit it directly.");
  process.exit(1);
}

// Look for a bundled template in the package root
const templateCandidates = [
  path.join(__dirname, "..", "templates", "config", "agentic-stlc.config.yaml.example"),
];

let content;
const template = templateCandidates.find(fs.existsSync);
if (template) {
  content = fs.readFileSync(template, "utf8");
} else {
  content = [
    "version: '1.0'",
    "project:",
    "  name: my-app",
    "  repository: ''",
    "target:",
    "  url: ''",
    "kaneai:",
    "  project_id: ''",
    "  folder_id: ''",
    "execution:",
    "  mode: incremental",
    "",
  ].join("\n");
}

fs.writeFileSync(dest, content, "utf8");

console.log(`\nCreated: ${dest}`);
console.log("\nNext steps:");
console.log("  1. Edit agentic-stlc.config.yaml — set project.repository and target.url");
console.log("  2. Run: agentic-stlc validate");
console.log("  3. Add requirements to requirements/search.txt");
console.log("  4. Run: agentic-stlc run\n");
