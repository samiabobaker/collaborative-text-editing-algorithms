from adopted.adoptedmessage import AdOPTedInsertionOperation
from adopted.adoptedtransform import SuleimanTransform
from unique_char.uniquechar import UniqueChar


# Suleiman et al. insert the character with the higher code first (Randolph et al.,
# figure 6), so the insert of b keeps its position and the insert of a shifts past it.
def test_suleiman_higher_character_goes_first():
    x = UniqueChar("b", 0)
    y = UniqueChar("a", 1)
    O1 = AdOPTedInsertionOperation(2, x, 1, set(), set(), {})
    O2 = AdOPTedInsertionOperation(2, y, 2, set(), set(), {})

    T1, T2 = SuleimanTransform().apply_transform(O1, O2)

    assert isinstance(T1, AdOPTedInsertionOperation)
    assert T1.position == 2
    assert isinstance(T2, AdOPTedInsertionOperation)
    assert T2.position == 3


if __name__ == "__main__":
    test_suleiman_higher_character_goes_first()
    print("OK")
