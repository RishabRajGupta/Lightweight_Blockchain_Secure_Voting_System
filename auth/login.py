"""Authentication helpers."""

from werkzeug.security import check_password_hash


def authenticate_voter(db, voter_id: str, password: str):
    voter = db.get_voter(voter_id)
    if voter and check_password_hash(voter["password_hash"], password):
        return voter
    return None
