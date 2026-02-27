class ModuleErrors:
    _messages: dict = {}

    @classmethod
    def get_message(cls, code, metadata: dict) -> str:
        template = cls._messages.get(code)

        if not template:
            return str(code)

        try:
            return template.format(**metadata)
        except KeyError as e:
            raise ValueError(
                f"Missing metadata key {e} for error {code}"
            )