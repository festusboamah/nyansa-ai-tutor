from .services import resolve_active_membership


class ActiveSchoolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.school = None
        request.school_membership = None
        if request.user.is_authenticated:
            membership = resolve_active_membership(request)
            if membership:
                request.school_membership = membership
                request.school = membership.school
        return self.get_response(request)
