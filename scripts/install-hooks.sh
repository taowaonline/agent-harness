#!/bin/sh
# Install the pre-push git hook.
#
# Philosophy (borrowed from dsh's lefthook.yml): local checkpoints stay
# fast; CI owns the full repository-wide gate matrix. This hook runs the
# named local gate `check` — the same lane CI runs — and nothing more.
#
# Regenerate rather than reject does not apply here: check is a read-only
# gate (format uses --check mode), so there is nothing to auto-fix.
#
# Install:  sh scripts/install-hooks.sh
# Uninstall: rm .git/hooks/pre-push

set -eu

HOOK=".git/hooks/pre-push"

if [ ! -d .git ]; then
    echo "install-hooks: run from the repository root" >&2
    exit 1
fi

cat > "$HOOK" <<'EOF'
#!/bin/sh
# Local checkpoint; CI owns the full matrix. See scripts/install-hooks.sh.
# Fast-path: skip entirely when the global opt-out is set.
if [ "${AGENT_HARNESS_NO_HOOKS:-}" = "1" ]; then
    exit 0
fi
exec ./agent_harness run check
EOF

chmod +x "$HOOK"
printf 'Installed pre-push hook -> %s\n' "$HOOK"
printf 'Opt out per-push with: AGENT_HARNESS_NO_HOOKS=1 git push\n'
