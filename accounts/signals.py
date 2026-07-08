from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def increment_login_count(sender, user, request, **kwargs):
    user.login_count += 1
    user.save(update_fields=["login_count"])