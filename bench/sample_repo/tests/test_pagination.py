from inventory.pagination import paginate


def test_paginate_first_page():
    items = list(range(10))
    # First page of 5 items should be [0, 1, 2, 3, 4]
    result = paginate(items, page=1, page_size=5)
    assert result == [0, 1, 2, 3, 4]


def test_paginate_second_page():
    items = list(range(10))
    # Second page of 5 items should be [5, 6, 7, 8, 9]
    result = paginate(items, page=2, page_size=5)
    assert result == [5, 6, 7, 8, 9]
