"""Database routing that keeps the core banking database read-only.

Two guarantees:
  1. Nothing from the `payments` app is ever written.
  2. No migration ever runs against the `cba` connection, so Django cannot
     create its own tables inside the banking schema.
"""


class ReadOnlyDatabaseError(Exception):
    """Raised when something attempts to write to the core banking database."""


class CbaRouter:
    app_label = "payments"
    db_alias = "cba"

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.db_alias
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            raise ReadOnlyDatabaseError(
                f"{model.__name__} lives in the read-only core banking database. "
                "This application never writes to it."
            )
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == self.db_alias:
            return False
        if app_label == self.app_label:
            return False
        return None
