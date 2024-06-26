import os
from contextlib import contextmanager
from typing import Generator, cast

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.sql import text


# make sure that foreign keys are enforced
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class SQLAlchemyWrapper:
    """
    Lightweight wrapper for SQL Alchemy DB access. The db object's associated DBManager
    is available at the db_manager property. This is not available for new DBs until the
    DB is populated by a db manager

    To create a new DB use create_empty_obj or:

    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy import String

    SQLAlchemyORMBase = declarative_base()
    class Product(SQLAlchemyORMBase):
       id = Column(Integer, primary_key=True)
       name = Column(String, nullable=False)

    db_obj = SQLAlchemyWrapper("filename.db")
    SQLAlchemyORMBase.metadata.create_all(db_obj.engine)

    To open an existing DB use get_db_obj or:

    db_obj = SQLAlchemyWrapper("filename.db")
    """

    def __init__(self, path_to_db_file=None, verbose=False, do_not_create=True):
        """
        path_to_db_file - if None then the DB will be in memory
        do_not_create - if True then first test that a file at path_to_db_file exists, and raise
           an exception if the file is not there. ignored if path_to_db_file is None
           (i.e. in memory DB)
        """
        if do_not_create and path_to_db_file is not None:
            if not os.path.isfile(path_to_db_file):
                raise FileNotFoundError(f"db file '{path_to_db_file}' not found")
        self.orig_path_to_db = path_to_db_file
        db_path = ("/" + path_to_db_file) if path_to_db_file is not None else ""
        self.engine = create_engine("sqlite://" + db_path, echo=verbose)
        self._SESSION_MAKER_FACTORY = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        """
        Create and return a new session.
        """
        return self._SESSION_MAKER_FACTORY()

    def execute(self, stmt, *params, **kwparams):
        """
        execute a statement directly on the engine

        For statements that don't need data...
        db_obj.execute("delete * from sometable")

        for selects the result is a typical resultset object, so do something like...
        db_obj.execute("select * from sometable").fetchall()

        IF you want to use parameters try something like...
        db_obj.execute("update sometable set col1 = :A where col2 = :B",
                       A=value_1, B=value_2)
        """
        if isinstance(stmt, str):
            stmt = text(stmt)
        with self.session_scoped() as session:
            return session.execute(stmt, *params, **kwparams)

    @staticmethod
    def get_pragma_user_version(engine) -> str:
        with sessionmaker(engine).begin() as session:
            version = cast(str, session.execute(text("pragma user_version")).fetchone()[0])
        return version

    def set_user_version(self, version):
        """set the the db id for the sport manager used to create the DB (use with caution)"""
        self.execute(f"pragma user_version = {version}")

    def set_readonly(self, readonly: bool):
        self.execute(f"pragma query_only = {'true' if readonly else 'false'}")

    @property
    def is_readonly(self):
        ro = self.execute(text("pragma query_only")).fetchone()[0]
        return ro

    @property
    def verbose(self):
        return self.engine.echo

    @verbose.setter
    def verbose(self, value):
        assert isinstance(value, bool)
        self.engine.echo = value

    @contextmanager
    def session_scoped(self) -> Generator[Session, None, None]:
        """
        context manager that yields a session, rollsback if there is an exception, otherwise commits
        at conclusion (unless autocommit is enabled in which case a closing commit is unneeded).
        http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#session-frequently-asked-questions

        to execute SQL using the session try...

        session.execute(sql, params={})

        where sql can contain named parameters of the form ':param_name' and the value for that
        parameter can be defined in the params dict
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()


def get_db_obj(
    path_to_db_file=None,
    verbose=False,
    sqlalchemy_wrapper=SQLAlchemyWrapper,
    do_not_create=True,
) -> SQLAlchemyWrapper:
    """
    do_not_create: if True and there is not already a file at path_to_db_file then raise
      FileNotFoundError, By default do not create a new DB
    """
    return sqlalchemy_wrapper(
        path_to_db_file=path_to_db_file, do_not_create=do_not_create, verbose=verbose
    )


def create_empty_db(
    sqlalchemy_orm_base,
    filename=None,
    verbose=False,
    sqlalchemy_wrapper=SQLAlchemyWrapper,
    overwrite_if_exists=False,
):
    """
    create a new db at filename

    filename - if None then create an in-memory DB (used for testing)
    overwrite_if_exists - if False and filename is not None and a file with that name exists then
       raise FileExistsError
    returns the db_obj reference to the database
    """
    if filename is not None and not overwrite_if_exists and os.path.isfile(filename):
        raise FileExistsError(f"file '{filename}' already exists")
    db_obj = get_db_obj(
        filename, verbose, do_not_create=False, sqlalchemy_wrapper=sqlalchemy_wrapper
    )
    sqlalchemy_orm_base.metadata.create_all(db_obj.engine)
    return db_obj
