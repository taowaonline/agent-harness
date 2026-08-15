# Post-mortem 0003: AppCard widget test crashed on a Vulkan-only shader

Status: resolved (in iLanguage commit `77128c4`)

## Executive summary

iLanguage's only failing Flutter widget test (`AppCard onTap fires via
ink well`) was not a logic bug at all. The Material 3 default splash,
`InkSparkle`, loads `shaders/ink_sparkle.frag`, which the Flutter SDK
ships compiled for Vulkan only. The widget-test runner uses the SkSL
backend, the shader fails to load, and the test throws before the tap
assertion runs — surfacing as "onTap didn't fire" and sending the
investigation to the wrong place (the widget) for two rounds.

## Impact

One permanently red test masking a toolchain mismatch; more subtly, the
same Vulkan-only shader can fail on older Android renderers in
production. The fix (theme-level `splashFactory: InkRipple`) resolved
both.

## Timeline

1. Harness integration surfaced `flutter test` failing on exactly one
   case: `ui_redesign_test.dart: AppCard onTap fires via ink well`
   (`206 passed, 5 skipped, 1 failed`).
2. Initial diagnosis assumed an `InkWell`/hit-test problem in `AppCard`;
   the widget code read correct.
3. Running the single test verbosely surfaced the real exception:
   `Exception: Asset 'shaders/ink_sparkle.frag' does not contain
   appropriate runtime stage data for current backend (SkSL). Found
   stages: Vulkan`.
4. Fix: `buildAppTheme` sets `splashFactory: InkRipple.splashFactory`
   globally; InkRipple is visually close and shader-free.
5. Full suite green: 207 passed, 5 skipped, 0 failed.

## Root cause

The test environment's rendering backend (SkSL) differs from the
production backend the shader was compiled for (Vulkan). A default
splash factory that depends on a single-backend shader makes every
widget test that triggers ink effects backend-coupled.

Process root cause: the failure message was in the logs all along, but
the "failing test name" (onTap fires) pointed at app logic, so the logs
were read only after the wrong hypothesis was exhausted.

## What the gates missed

Nothing actionable — the gate (the test) fired correctly. The lesson is
about reading order: for a failing test, read the exception before the
test name.

## Fix and the rule it produced

Rules:

1. **Read the exception before the test name.** The test's title is a
   hypothesis; the stack trace is evidence.
2. Prefer shader-free, backend-independent splash/ink effects in theme
   defaults; a theme default that breaks on one backend breaks every
   widget test that touches it.
3. When exactly one test fails while its siblings pass, suspect the
   environment before the code under test.
