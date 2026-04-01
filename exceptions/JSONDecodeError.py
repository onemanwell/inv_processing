class JSONDecodeError(Exception):
    def __init__(self, description):
        self._description = description