from functools import lru_cache


class Columns(dict):

    def __init__(self, row_dict):
        super().__init__({
            Columns.make_key(key): value for key, value in row_dict.items()
        })

    @classmethod
    def from_keys(cls, keys):
        return cls({key: key for key in keys})

    def __getitem__(self, key):
        return super().get(Columns.make_key(key))

    def get(self, key, default=None):
        try:
            return self[key]
        except IndexError:
            return default

    def copy(self):
        return Columns(super().copy())

    def as_dict_with_keys(self, keys):
        return {
            key: self.get(key) for key in keys
        }

    @staticmethod
    @lru_cache(maxsize=32, typed=False)
    def make_key(original_key):
        if original_key is None:
            return None
        return "".join(
            character.lower() for character in original_key if character not in ' _-'
        )


class Row(Columns):

    message_too_long = False

    def __init__(
        self,
        row_dict,
        index,
        error_fn,
        placeholders,
        template,
    ):

        self.index = index

        if template:
            template.values = row_dict
            self.message_too_long = template.is_message_too_long()

        super().__init__({
            key: Cell(key, value, error_fn, placeholders)
            for key, value in row_dict.items()
        })

    def get(self, key):
        return super().get(key) or Cell()


class Cell():

    def __init__(
        self,
        key=None,
        value=None,
        error_fn=None,
        placeholders=None
    ):
        self.data = value
        self.error = error_fn(key, value) if error_fn else None
        self.ignore = Columns.make_key(key) not in (placeholders or [])
