import sys


class DictContains:
    def __init__(self, subdict: dict):  # type: ignore[type-arg]
        self.subdict = subdict

    def __eq__(self, other):
        assert isinstance(other, dict)

        for key, value in self.subdict.items():
            if other[key] != value:
                print("NOT MATCHED:", key, value, other[key], file=sys.stderr)  # noqa
                return False
        return True

    def __str__(self):
        return f"<dict should contain fields {self.subdict!r}"

    def __repr__(self):
        return self.__str__()
