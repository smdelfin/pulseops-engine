# Runtime: Imports regular-expression helpers for stable tag normalization.
# Architecture: Prevents provider-specific spelling rules from leaking into callers.
# Plain English: Prepares to turn cohort names into consistent filter tags.
import re


# Runtime: Builds ClickUp tag names from student fields shared by demo and production provisioning.
# Architecture: Keeps segmentation labels consistent across direct and queued task creation.
# Plain English: Labels a student task by cohort, health band, and program category.
def build_student_tags(cohort: str, health_score: int | None) -> list[str]:
    # Runtime: Normalizes cohort text into a lowercase hyphen-delimited label.
    # Architecture: Makes human-entered cohort names reliable list filters.
    # Plain English: Converts a cohort name such as "Cohort 8" into "cohort-8".
    cohort_slug = re.sub(r"[^a-z0-9]+", "-", cohort.strip().lower()).strip("-")
    cohort_tag = (
        cohort_slug
        if cohort_slug.startswith("cohort-")
        else f"cohort-{cohort_slug or 'unspecified'}"
    )

    # Runtime: Selects a health label using consistent score thresholds.
    # Architecture: Makes low-health students visually filterable in the ClickUp cockpit.
    # Plain English: Marks students green, amber, red, or unknown based on their score.
    if health_score is None:
        health_tag = "health-unknown"
    elif health_score < 50:
        health_tag = "health-red"
    elif health_score < 80:
        health_tag = "health-amber"
    else:
        health_tag = "health-green"

    # Runtime: Returns the normalized labels ClickUp attaches to the task.
    # Architecture: Provides stable cross-record tags for cohort and health views.
    # Plain English: Adds cohort, health, and program-category filters to the card.
    return [cohort_tag, health_tag, "high-ticket"]
