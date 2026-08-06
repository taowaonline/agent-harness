# Prompts

Prompts are first-class versioned artifacts, not strings sprinkled
through business code.

## Layout

```
prompts/
├── README.md
├── manifest.example.toml
├── schemas/                   # JSON schemas for inputs/outputs
│   ├── support-input.json
│   └── support-output.json
└── templates/                 # Prompt template bodies
    └── support-answer.md
```

A real project copies this layout and fills in real prompts. The harness
itself does not load prompts at runtime — that is the application's
responsibility — but it tracks prompt versions in eval reports.

## Manifest

Each prompt has a manifest entry. See `manifest.example.toml`:

```toml
id = "support-answer"
version = "1.2.0"
template = "templates/support-answer.md"
input_schema = "schemas/support-input.json"
output_schema = "schemas/support-output.json"
owner = "team-name"
```

Rules:

- Bump `version` on any behavioral change to the template, schemas, or
  referenced tools.
- A prompt change is a release — see `docs/release-policy.md`.
- The harness records the active prompt id/version in the eval report
  when the project supplies it (via the `ModelProvider` integration).

## Build-time embedding

Prompt bodies may be embedded into application binaries at build time
(e.g. via `include_str!` in Rust, `import` in Python with a loader, or
`fs.readFileSync` in Node). The source file under `prompts/` remains the
source of truth and is reviewable in PRs.

## What not to do

- Do not store prompt text inline in service code.
- Do not commit prompt variants under undocumented names like
  `support-answer-v2-final.md`.
- Do not change a prompt without bumping its manifest version.
