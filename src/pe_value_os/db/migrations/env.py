"""Alembic environment. Migrations are raw SQL; there is no ORM metadata to autogenerate from."""

from alembic import context
from sqlalchemy import create_engine

from pe_value_os.db.migrate import sqlalchemy_url

config = context.config


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or sqlalchemy_url()
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
