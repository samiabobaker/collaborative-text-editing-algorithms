class UniqueChar:
    now = 0

    char: str 
    id: int

    def __init__(self, char: str, id: int) -> None:
        self.char = char
        self.id = id

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f"({self.char}:{self.id})"

    @staticmethod
    def get_unique_char(char: str) -> UniqueChar:
        c = UniqueChar(char, UniqueChar.now)
        UniqueChar.now += 1
        return c