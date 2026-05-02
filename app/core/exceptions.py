from fastapi import HTTPException, status


class UnsupportedFileTypeError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported file type. "
                "Accepted formats: Excel (.xlsx, .xlsm, .xltx, .xltm), "
                "Word (.docx, .doc), PDF (.pdf)."
            ),
        )


class JobNotFoundError(HTTPException):
    def __init__(self, job_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )


class JobNotCompletedError(HTTPException):
    def __init__(self, status: str) -> None:
        super().__init__(
            status_code=409,
            detail=f"Job is not completed yet. Current status: {status}",
        )


class ResultFileMissingError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result file is missing. Re-submit the job.",
        )
