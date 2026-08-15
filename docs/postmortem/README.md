# Post-mortems

Numbered incident write-ups. Each records what broke, why the existing
gates missed it, and the rule that now exists because of it. Policy docs
cite these by number — a rule with a post-mortem behind it is a rule with
evidence.

Format: Executive summary → Impact → Timeline → Root cause → What the
gates missed → Fix and the rule it produced.

| # | Incident | Rule it produced |
|---|---|---|
| [0001](0001-github-secret-scanning-blocked-pushes.md) | GitHub secret scanning blocked three consecutive pushes | Never write secret-shaped literals; construct at runtime; grep before push |
| [0002](0002-ilanguage-verifytoken-utf8-corruption.md) | verifyToken silently failed all tokens (base64→UTF-8 detour) | First test coverage on untested code surfaces latent bugs; decode base64 straight to bytes |
| [0003](0003-inksparkle-shader-skl-backend.md) | AppCard widget test crashed on Vulkan-only shader | Prefer shader-free splash in theme; test-runner backend ≠ runtime backend |
