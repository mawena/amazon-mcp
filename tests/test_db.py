from amazon_mcp import db


def make_conn(tmp_path):
    return db.get_conn(tmp_path / "test.db")


def test_track_and_list(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "https://www.amazon.fr/dp/B000000001", "Clavier")
    rows = db.list_tracked(conn)
    assert len(rows) == 1
    assert rows[0]["asin"] == "B000000001"
    assert rows[0]["label"] == "Clavier"
    assert rows[0]["last_price"] is None


def test_track_idempotent(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    db.add_tracked(conn, "B000000001", "u")
    assert len(db.list_tracked(conn)) == 1


def test_untrack(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    assert db.remove_tracked(conn, "B000000001") is True
    assert db.remove_tracked(conn, "B000000001") is False
    assert db.list_tracked(conn) == []


def test_is_tracked(tmp_path):
    conn = make_conn(tmp_path)
    assert db.is_tracked(conn, "B000000001") is False
    db.add_tracked(conn, "B000000001", "u")
    assert db.is_tracked(conn, "B000000001") is True


def test_price_history_and_last_price(tmp_path):
    conn = make_conn(tmp_path)
    db.add_tracked(conn, "B000000001", "u")
    db.record_price(conn, "B000000001", 29.99, "EUR", True)
    db.record_price(conn, "B000000001", 24.99, "EUR", True)
    hist = db.price_history(conn, "B000000001")
    assert [h["price"] for h in hist] == [29.99, 24.99]
    row = db.list_tracked(conn)[0]
    assert row["last_price"] == 24.99
    assert row["previous_price"] == 29.99
