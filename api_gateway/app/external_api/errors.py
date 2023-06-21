class ExternalAPIError(Exception):
    pass


class EAPIClientError(ExternalAPIError):
    pass


class EAPIServerError(ExternalAPIError):
    def __init__(self, status_code: int, error_code: int, message: str):
        super().__init__(status_code, error_code, message)

    @property
    def status_code(self):
        return self.args[0]

    @property
    def error_code(self):
        return self.args[1]

    @property
    def message(self):
        return self.args[2]

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


class EAPIResponseParseError(ExternalAPIError):
    def __init__(self):
        super().__init__("Failed to parse server response")
