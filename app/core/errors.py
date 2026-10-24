"""Domain errors are translated to HTTP responses at the application boundary."""


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class InvalidRequestError(Exception):
    pass
