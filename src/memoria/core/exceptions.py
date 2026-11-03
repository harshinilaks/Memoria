from fastapi import HTTPException, status


class MemoryNotFoundError(HTTPException):
    def __init__(self, memory_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory with id {memory_id} not found",
        )


class NamespaceConflictError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class ValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )
