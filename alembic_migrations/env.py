"""Alembic environment — Flask app context, multi-dialect batch mode.

Existing SQLite production databases may still have a legacy ``schema_migrations``
table from the pre-Alembic runner. That table is historical only; Alembic tracks
applied revisions in ``alembic_version``. Do not drop ``schema_migrations`` on
upgrade — stamp ``head`` on fully-migrated databases instead of re-running DDL.
"""

import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine():
    try:
        return current_app.extensions["migrate"].db.get_engine()
    except (TypeError, AttributeError):
        return current_app.extensions["migrate"].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def _configure_context(connection, **extra):
    """Shared Alembic context options for online/offline runs."""
    dialect_name = connection.dialect.name if connection is not None else None
    if dialect_name is None:
        url = config.get_main_option("sqlalchemy.url") or ""
        dialect_name = "sqlite" if url.startswith("sqlite") else "postgresql"

    render_as_batch = dialect_name == "sqlite"
    conf_args = dict(current_app.extensions["migrate"].configure_args)
    conf_args.setdefault("compare_type", True)
    conf_args["render_as_batch"] = render_as_batch
    conf_args.update(extra)

    if connection is not None:
        context.configure(connection=connection, target_metadata=get_metadata(), **conf_args)
    else:
        context.configure(
            url=config.get_main_option("sqlalchemy.url"),
            target_metadata=get_metadata(),
            literal_binds=True,
            **conf_args,
        )


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    _configure_context(None)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""

    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    connectable = get_engine()

    with connectable.connect() as connection:
        _configure_context(connection, process_revision_directives=process_revision_directives)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
