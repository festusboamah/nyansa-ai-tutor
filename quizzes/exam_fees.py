"""
Fee-gate for exams. This is a deliberate, documented exception to the
"no keep-side app imports a frozen app" rule in AGENTS.md: this is the single,
isolated, read-only call site into `finance`. See AGENTS.md ("Frozen apps")
for the full rationale.
"""
from .models import ExamFeeWaiver


def fee_balance_blocks_exam(membership, quiz):
    """
    Returns True if `membership` (a schools.SchoolMembership) should be blocked
    from sitting `quiz` due to an outstanding fee balance, unless waived.
    """
    if ExamFeeWaiver.objects.filter(student=membership, quiz=quiz).exists():
        return False

    return get_fee_balance(membership) > 0


def get_fee_balance(membership):
    """Read-only fee balance for display (e.g. on the exam roster page)."""
    from finance.services import ledger_summary

    return ledger_summary(membership)["balance"]
