#!/usr/bin/env node
/**
 * agent-harness setup — wire the harness skill into coding agent CLIs.
 *
 * Targets (each is independent; run with no flags to install everything):
 *   --claude        ~/.claude/skills/agent-harness      (Claude Code)
 *   --zcode         ~/.zcode/skills/agent-harness       (Z.ai ZCode)
 *   --kimi          ~/.kimi-code/skills/agent-harness   (Kimi Code CLI)
 *   --agents-shared ~/.agents/skills/agent-harness      (cross-tool shared dir)
 *   --deepcode      ~/.deepcode/skills/agent-harness    (Deep Code, best-effort)
 *   --codex         managed block in ~/.codex/AGENTS.md (+ project AGENTS.md with --project)
 *   --cursor        <project>/.cursor/rules/agent-harness.mdc (--project, defaults to cwd)
 *
 * Other flags: --all, --force, --uninstall, --list, --project <dir>
 *
 * SKILL.md targets are symlinks to the package root (updates via
 * `npm update -g` are picked up live); falls back to copying when symlinks
 * are unavailable (e.g. Windows without developer mode).
 */

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

const PKG_ROOT = path.resolve(__dirname, "..");
const SKILL_NAME = "agent-harness";
const START_MARK = "<!-- agent-harness:start -->";
const END_MARK = "<!-- agent-harness:end -->";

// SKILL.md-skill targets: flag -> { dir, label }
const SKILL_TARGETS = {
  claude: { dir: ".claude/skills", label: "Claude Code" },
  zcode: { dir: ".zcode/skills", label: "Z.ai ZCode" },
  kimi: { dir: ".kimi-code/skills", label: "Kimi Code CLI" },
  "agents-shared": { dir: ".agents/skills", label: "shared ~/.agents (cross-tool)" },
  deepcode: { dir: ".deepcode/skills", label: "Deep Code (best-effort)" },
};

function usage(code) {
  const text = [
    "Usage: agent-harness-setup [flags]",
    "",
    "  (no flags)            install all SKILL.md targets + codex global block",
    "  --claude              ~/.claude/skills (Claude Code)",
    "  --zcode               ~/.zcode/skills (Z.ai ZCode)",
    "  --kimi                ~/.kimi-code/skills (Kimi Code CLI)",
    "  --agents-shared       ~/.agents/skills (cross-tool shared standard)",
    "  --deepcode            ~/.deepcode/skills (Deep Code, best-effort)",
    "  --codex               managed block in ~/.codex/AGENTS.md",
    "  --cursor              .cursor/rules/agent-harness.mdc in --project dir",
    "  --project <dir>       project dir for --cursor / codex project block (default: cwd)",
    "  --all                 every target above (cursor uses --project)",
    "  --force               replace existing installs",
    "  --uninstall           remove installs instead of adding them",
    "  --list                show targets and exit",
    "",
    "Package root: " + PKG_ROOT,
  ].join("\n");
  (code === 0 ? console.log : console.error)(text);
  process.exit(code);
}

function parseArgs(argv) {
  const opts = {
    targets: new Set(),
    project: process.cwd(),
    force: false,
    uninstall: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--force") opts.force = true;
    else if (a === "--uninstall") opts.uninstall = true;
    else if (a === "--list") opts.list = true;
    else if (a === "--help" || a === "-h") usage(0);
    else if (a === "--project") {
      const next = argv[i + 1];
      if (!next) usage(1);
      opts.project = path.resolve(next);
      i++;
    } else if (a === "--all") {
      for (const k of Object.keys(SKILL_TARGETS)) opts.targets.add(k);
      opts.targets.add("codex");
      opts.targets.add("cursor");
    } else if (SKILL_TARGETS[a.slice(2)] || a === "--codex" || a === "--cursor") {
      opts.targets.add(a.slice(2));
    } else {
      console.error(`unknown flag: ${a}`);
      usage(1);
    }
  }
  if (opts.targets.size === 0 && !opts.list) {
    for (const k of Object.keys(SKILL_TARGETS)) opts.targets.add(k);
    opts.targets.add("codex");
  }
  return opts;
}

function homeDir() {
  // Honor HOME on unix; os.homedir() covers Windows and macOS defaults.
  return process.env.HOME || os.homedir();
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function skillLinkLabel(target) {
  return SKILL_TARGETS[target].label;
}

function installSkill(target, opts) {
  const skillsDir = path.join(homeDir(), SKILL_TARGETS[target].dir);
  const dest = path.join(skillsDir, SKILL_NAME);
  const action = opts.uninstall ? "uninstall" : "install";
  if (opts.uninstall) {
    if (!fs.existsSync(dest)) {
      console.log(`  [${target}] not installed — nothing to do`);
      return;
    }
    fs.rmSync(dest, { recursive: true, force: true });
    console.log(`  [${target}] removed ${dest}`);
    return;
  }
  let st = null;
  try {
    st = fs.lstatSync(dest); // works for broken symlinks too
  } catch (_) {
    st = null; // not present
  }
  if (st) {
    if (st.isSymbolicLink() && fs.realpathSync(dest) === PKG_ROOT) {
      console.log(`  [${target}] already installed -> ${dest}`);
      return;
    }
    if (!opts.force) {
      console.log(`  [${target}] SKIP (exists, not pointing at this package): ${dest}`);
      return;
    }
    fs.rmSync(dest, { recursive: true, force: true });
  }
  ensureDir(skillsDir);
  try {
    fs.symlinkSync(PKG_ROOT, dest, "dir");
    console.log(`  [${target}] linked ${dest} -> ${PKG_ROOT}`);
  } catch (_) {
    fs.cpSync(PKG_ROOT, dest, { recursive: true });
    console.log(`  [${target}] copied (symlink unavailable) -> ${dest}`);
  }
}

function readManagedBlock() {
  const snippet = fs.readFileSync(path.join(PKG_ROOT, "adapters", "agents-snippet.md"), "utf8");
  return `${START_MARK}\n${snippet.trimEnd()}\n${END_MARK}`;
}

function upsertAgentsFile(file, block, opts) {
  const existing = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "";
  const s = existing.indexOf(START_MARK);
  const e = existing.indexOf(END_MARK);
  if (opts.uninstall) {
    if (s === -1 || e === -1) return false;
    const before = existing.slice(0, s);
    const after = existing.slice(e + END_MARK.length).replace(/^\n+/, "\n");
    fs.writeFileSync(file, before + after, "utf8");
    return true;
  }
  if (s !== -1 && e !== -1) {
    const updated =
      existing.slice(0, s) + block + existing.slice(e + END_MARK.length);
    if (updated === existing) return false;
    fs.writeFileSync(file, updated, "utf8");
    return true;
  }
  const sep = existing && !existing.endsWith("\n") ? "\n\n" : existing ? "\n" : "";
  fs.writeFileSync(file, existing + sep + block + "\n", "utf8");
  return true;
}

function installCodex(opts) {
  const block = readManagedBlock();
  const globalFile = path.join(homeDir(), ".codex", "AGENTS.md");
  if (opts.uninstall) {
    const removed = upsertAgentsFile(globalFile, block, opts);
    console.log(
      removed
        ? `  [codex] removed managed block from ${globalFile}`
        : `  [codex] no managed block in ${globalFile}`
    );
    return;
  }
  ensureDir(path.dirname(globalFile));
  const changed = upsertAgentsFile(globalFile, block, opts);
  console.log(
    changed
      ? `  [codex] wrote managed block -> ${globalFile}`
      : `  [codex] managed block already up to date in ${globalFile}`
  );
}

function installCursor(opts) {
  const rulesDir = path.join(opts.project, ".cursor", "rules");
  const dest = path.join(rulesDir, "agent-harness.mdc");
  const src = path.join(PKG_ROOT, "adapters", "cursor-rule.mdc");
  if (opts.uninstall) {
    if (fs.existsSync(dest)) {
      fs.rmSync(dest, { force: true });
      console.log(`  [cursor] removed ${dest}`);
    } else {
      console.log(`  [cursor] not installed in ${opts.project}`);
    }
    return;
  }
  ensureDir(rulesDir);
  fs.copyFileSync(src, dest);
  console.log(`  [cursor] wrote ${dest}`);
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.list) {
    console.log(`package root: ${PKG_ROOT}`);
    for (const [flag, t] of Object.entries(SKILL_TARGETS)) {
      const dest = path.join(homeDir(), t.dir, SKILL_NAME);
      const state = fs.existsSync(dest) ? "installed" : "not installed";
      console.log(`  --${flag.padEnd(14)} ${dest}  (${state}, ${t.label})`);
    }
    console.log(`  --codex          ${path.join(homeDir(), ".codex", "AGENTS.md")}`);
    console.log(`  --cursor         ${path.join(opts.project, ".cursor", "rules", "agent-harness.mdc")}`);
    return 0;
  }
  console.log(
    opts.uninstall ? `agent-harness: uninstalling from ${homeDir()}` : `agent-harness: installing from ${PKG_ROOT}`
  );
  let acted = 0;
  for (const target of opts.targets) {
    if (SKILL_TARGETS[target]) {
      installSkill(target, opts);
      acted++;
    } else if (target === "codex") {
      installCodex(opts);
      acted++;
    } else if (target === "cursor") {
      installCursor(opts);
      acted++;
    }
  }
  if (!opts.uninstall && opts.targets.has("deepcode")) {
    console.log(
      `  [deepcode] note: path is a best-effort guess; if your Deep Code build reads skills from elsewhere, symlink ${path.join(homeDir(), ".deepcode", "skills", SKILL_NAME)} manually`
    );
  }
  console.log(opts.uninstall ? "done (uninstall)" : "done");
  return acted > 0 || opts.uninstall ? 0 : 1;
}

process.exit(main());
