from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class BurstRateThrottle(UserRateThrottle):
    """
    Throttle for short burst protection (e.g., 60 requests/minute).
    """
    scope = 'burst'


class SustainedRateThrottle(UserRateThrottle):
    """
    Throttle for daily sustained usage limits.
    """
    scope = 'sustained'


class UploadThrottle(UserRateThrottle):
    """
    Throttle for file upload endpoints.
    """
    scope = 'upload'


class ChunkedUploadThrottle(UserRateThrottle):
    """
    Throttle for chunked upload endpoints.
    Higher rate to allow multiple chunks per file upload.
    """
    scope = 'chunked_upload'


class CreateThrottle(UserRateThrottle):
    """
    Throttle for create/POST operations.
    """
    scope = 'create'


class AuthThrottle(AnonRateThrottle):
    """
    Strict throttle for authentication endpoints to prevent brute force.
    """
    scope = 'auth'


class StrictAnonThrottle(AnonRateThrottle):
    """
    Stricter throttle for anonymous users on sensitive endpoints.
    """
    rate = '20/hour'
