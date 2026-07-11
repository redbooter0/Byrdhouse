"""Deterministic guardrails for Image Studio draft persistence and safe polling."""

from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text()


def check(label, expected):
    if not expected:
        raise AssertionError(label)
    print(f"PASS {label}")


check("draft has a stable localStorage key", "const IMAGE_DRAFT_KEY = 'bh_image_studio_draft_v1'" in SOURCE)
check("every Image Studio input and change saves the draft",
      "form.addEventListener('input', saveImageDraft)" in SOURCE and
      "form.addEventListener('change'" in SOURCE)
check("draft restores recipe, slots, title, project, and purpose",
      all(token in SOURCE for token in ("draft.recipe", "draft.slots", "draft.title", "draft.project", "draft.purpose")))
check("successful queue clears storage only after the POST resolves",
      SOURCE.index("const j = await jpost('/jobs'") < SOURCE.index('clearImageDraft();'))
check("Image Studio polling refreshes its gallery instead of replacing the form",
      "if (targetRoom === 'image' && $('imageStudio'))" in SOURCE and "await refreshImageOutput();" in SOURCE)
check("polling guards against overlapping ticks and renders",
      "if (ticking) return;" in SOURCE and "if (rendering) { renderPending = true; return; }" in SOURCE)
