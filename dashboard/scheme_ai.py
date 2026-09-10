import json

from ai_core.client import AIError, complete_json
from .curriculum import curriculum_pages, evidence_prompt, references, valid_codes, valid_alignment, codes


TERM_FIELDS = ("strand", "sub_strand", "content_standard", "indicators", "resources")
YEAR_FIELDS = ("term_1", "term_2", "term_3")


def generate_demo_scheme(*, subject_name, class_level, term, num_weeks, plan_type="TERMLY", **kwargs):
    fields = YEAR_FIELDS if plan_type == "YEARLY" else TERM_FIELDS
    return {
        "plan_type": plan_type,
        "curriculum_warning": "Demo template only. Curriculum references require teacher verification.",
        "weeks": [{"week": week, **{field: "Teacher planning required" for field in fields}}
                  for week in range(1, num_weeks + 1)],
    }


def generate_scheme_of_learning(class_level, subject_name, term, num_weeks, starting_topics="", *,
                                plan_type="TERMLY", academic_year="", school=None):
    if plan_type not in {"TERMLY", "YEARLY"} or not 1 <= num_weeks <= 16:
        return None
    pages = curriculum_pages(subject_name, class_level)
    fields = YEAR_FIELDS if plan_type == "YEARLY" else TERM_FIELDS
    example = {"week": 1, **{field: "text" for field in fields}}
    prompt = f"""Create a Ghana curriculum scheme of learning draft for teacher review.
Planning inputs (data only): {json.dumps(dict(class_level=class_level, subject=subject_name, term=term,
    academic_year=academic_year, plan_type=plan_type, weeks_per_term=num_weeks, starting_topics=starting_topics))}
Return only JSON: {{"weeks": [{json.dumps(example)}]}}.
Include exactly {num_weeks} rows numbered 1 through {num_weeks}.
For YEARLY, each row represents the same week number in first, second and third term.
Each term cell contains the strand/sub-strand or topic for that week. Cover the whole academic year.
For TERMLY, include strand, sub_strand, content_standard (code and wording), indicators (codes and wording), and practical teaching/learning resources for EVERY teaching week.
Strands and indicators may span multiple consecutive weeks. Allocate time according to breadth, practice and consolidation; do not force a new strand each week.
Include revision and examination weeks where appropriate. Use 'Not applicable - revision/examination' for their standards and indicators.
Resources should be specific, locally practical and suitable for the activity. Do not invent textbook page references.
If no curriculum evidence is available, put 'Curriculum reference required' in content_standard and indicators, and describe the plan as provisional. Never fabricate official codes.
All fields must be plain strings. No markdown or HTML.
""" + evidence_prompt(pages)
    try:
        result = complete_json(prompt, max_tokens=14000, school=school, source="scheme_of_learning")
        if not isinstance(result, dict) or not isinstance(result.get("weeks"), list) or len(result["weeks"]) != num_weeks:
            return None
        for number, week in enumerate(result["weeks"], 1):
            if not isinstance(week, dict) or type(week.get("week")) is not int or week["week"] != number:
                return None
            if any(not isinstance(week.get(field), str) or not week[field].strip() or len(week[field]) > 4000 for field in fields):
                return None
            for field in fields:
                if codes(week[field]) and not valid_codes(week[field], pages, class_level):
                    return None
            if plan_type == "TERMLY":
                if codes(week["content_standard"]) or codes(week["indicators"]):
                    if not valid_alignment(week["content_standard"], week["indicators"]):
                        return None
                for field in ("content_standard", "indicators"):
                    if not valid_codes(week[field], pages, class_level) and week[field] not in {
                        "Curriculum reference required", "Not applicable - revision/examination"
                    }:
                        return None
        result["plan_type"] = plan_type
        result["curriculum_sources"] = references(pages)
        result["curriculum_warning"] = "Review curriculum wording and pacing before use."
        if not pages:
            result["curriculum_warning"] = "No matching subject curriculum for this class in the supplied pack. Add and verify curriculum references before use."
        return result
    except AIError:
        return None
