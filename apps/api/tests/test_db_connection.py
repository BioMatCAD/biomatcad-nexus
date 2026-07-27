from sqlalchemy import text


def test_can_execute_simple_query(db_session):
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
