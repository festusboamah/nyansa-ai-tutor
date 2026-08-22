from django.db import models


class IntegrationCredential(models.Model):
    """One active API credential per school. Regenerating replaces the token,
    immediately invalidating the previous one - only the SHA-256 hash of the
    plaintext token is ever stored; the plaintext is shown once at creation."""

    school = models.OneToOneField(
        "schools.School", on_delete=models.CASCADE, related_name="integration_credential"
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey("schools.SchoolMembership", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"API credential for {self.school.name}"
