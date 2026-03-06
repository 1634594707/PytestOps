import pytest

from ntf.assertions import AssertionEngine


def test_assertions_extended_ops_pass():
    engine = AssertionEngine()
    actual = {
        "code": 200,
        "msg": "hello world",
        "score": 88,
        "role": "admin",
        "name": "alice_001",
        "data": {"count": 3},
    }

    expected = [
        {"contains": {"msg": "hello"}},
        {"eq": {"code": 200}},
        {"ne": {"code": 500}},
        {"lt": {"score": 100}},
        {"lte": {"score": 88}},
        {"gt": {"score": 10}},
        {"gte": {"score": 88}},
        {"in": {"role": ["admin", "user"]}},
        {"not_in": {"role": ["guest", "visitor"]}},
        {"regex": {"name": r"^alice_\d+$"}},
        {"eq": {"$.data.count": 3}},
    ]

    engine.assert_all(expected, actual, status_code=200)


def test_assertions_failure_message_has_kind_locator_expected_actual():
    engine = AssertionEngine()
    actual = {"msg": "ok"}

    with pytest.raises(AssertionError) as ei:
        engine.assert_all([{"eq": {"msg": "failed"}}], actual, status_code=200)

    msg = str(ei.value)
    assert "eq:" in msg
    assert "locator=msg" in msg
    assert "expected='failed'" in msg
    assert "actual='ok'" in msg


def test_assertions_jsonschema_optional():
    pytest.importorskip("jsonschema")

    engine = AssertionEngine()
    actual = {"id": 1, "name": "n"}
    expected = [
        {
            "jsonschema": {
                "type": "object",
                "required": ["id", "name"],
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            }
        }
    ]

    engine.assert_all(expected, actual, status_code=200)
