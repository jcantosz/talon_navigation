import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import process from "node:process";
import { talonFormatter } from "@cursorless/talon-tools";
import { getOptionsFromConfig } from "@cursorless/talon-tools/node";
import { Language, Parser } from "web-tree-sitter";

const args = process.argv.slice(2);
const fix = args.includes("--fix");
const files = args.filter((arg) => arg !== "--fix");
if (!files.length) {
  throw new Error("No Talon files supplied.");
}

// Use the public formatter API; the published CLI assumes a nested npm layout.
const require = createRequire(import.meta.url);
const wasm = require.resolve("@cursorless/tree-sitter-wasms/out/tree-sitter-talon.wasm");
await Parser.init();
const parser = new Parser();
parser.setLanguage(await Language.load(wasm));
let failed = false;

function syntaxErrors(node, file) {
  if (node.isError || node.isMissing) {
    const { row, column } = node.startPosition;
    console.error(`${file}:${row + 1}:${column + 1}: invalid Talon syntax (${node.type})`);
    return;
  }
  for (const child of node.children) {
    if (child.hasError || child.isMissing) syntaxErrors(child, file);
  }
}

try {
  for (const file of files) {
    const source = await readFile(file, "utf8");
    const tree = parser.parse(source);
    if (!tree) throw new Error(`Unable to parse ${file}`);
    try {
      if (tree.rootNode.hasError) {
        syntaxErrors(tree.rootNode, file);
        failed = true;
        continue;
      }
      const options = await getOptionsFromConfig(file);
      let formatted = talonFormatter(tree.rootNode, options);
      let stable = false;
      // The pinned formatter removes an empty header and its blank line in separate passes.
      for (let pass = 0; pass < 3; pass++) {
        const reparsed = parser.parse(formatted);
        if (!reparsed) throw new Error(`Unable to parse formatter output for ${file}`);
        try {
          if (reparsed.rootNode.hasError) {
            throw new Error(`Formatter produced invalid Talon syntax for ${file}`);
          }
          const next = talonFormatter(reparsed.rootNode, options);
          if (next === formatted) {
            stable = true;
            break;
          }
          formatted = next;
        } finally {
          reparsed.delete();
        }
      }
      if (!stable) throw new Error(`Formatter did not converge for ${file}`);
      if (source !== formatted) {
        if (fix) {
          await writeFile(file, formatted, "utf8");
          console.log(`Formatted ${file}`);
        } else {
          console.error(`${file}: formatting differs (run scripts/check.py --fix)`);
          failed = true;
        }
      }
    } finally {
      tree.delete();
    }
  }
} finally {
  parser.delete();
}
process.exitCode = failed ? 1 : 0;
