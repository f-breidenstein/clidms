#! /usr/bin/env python3
import os
import sys
import logging
import click
import subprocess
from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.engine.reflection import Inspector
import texttable as tt


Base = declarative_base()

association_table = Table('association', Base.metadata,
    Column('document_id', Integer, ForeignKey('Document.id')),
    Column('tag_id', Integer, ForeignKey('Tag.id'))
)

class Document(Base):
    __tablename__ = "Document"
    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    filename = Column(String(250), nullable=False)
    tags = relationship("Tag",
                    secondary=association_table)
    def __repr__(self):
        return "Document <{}>".format(self.filename)


class Tag(Base):
    __tablename__ = "Tag"
    id = Column(Integer, primary_key=True)
    value = Column(String(50), nullable=False)

    def __repr__(self):
        return self.value


xdg_config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
config_dir = os.path.join(xdg_config_home, 'clidms')
config_file = os.path.join(config_dir, 'config.py')

if not os.path.isdir(config_dir) or not os.path.isfile(config_file):
    logging.warning('There is no config.py in {}'.format(config_dir))
else:
    sys.path.insert(0, config_dir)

    try:
        import config
    except ImportError as ie:
        exc_info = sys.exc_info()

        logging.critical("Failed to import config file. current sys.path is {}".format(sys.path))
        logging.critical("The error during import was: {}".format(traceback.format_exception(*exc_info)))

DB_PATH = "sqlite:///{}/clidms.sqlite".format(config.DATA_PATH)
engine = create_engine(DB_PATH)
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

@click.group()
def clidms():
    pass

@clidms.command("index")
@click.option("-r", "--recursive", help="Scan the DOCUMENT_PATH dir recursively", default=False, is_flag=True)
def index_documents(recursive):
    inspector = Inspector.from_engine(engine)
    if not "Document" in inspector.get_table_names():
        logging.warning('There is no database in the data folder. Creating a new one for you')
        create_db()

    try:
        files = os.listdir(config.DOCUMENT_PATH)
    except FileNotFoundError:
        logging.critical("Document folder does not exist ({})".format(config.DOCUMENT_PATH))
        exit(1)

    supported_files = [f for f in files if f.split(".")[-1] in config.SUPPORTED_FILETYPES]
    print("Found {} files".format(len(supported_files)))
    new_files = 0

    for f in  supported_files:
        if not session.query(Document).filter_by(filename=f).all():
            new_doc = Document(filename=f, name=f)
            session.add(new_doc)
            new_files = new_files + 1

    session.commit()
    print("Indexed {} new files.".format(new_files))

@clidms.command("list")
@click.option("-l", "--limit", help="Limit the amount of results to show", default=10)
def list_documents(limit):
    if limit == 0:
        print_table(session.query(Document).all())
    else:
        print_table(session.query(Document).limit(limit))


def print_table(documents):
    tab = tt.Texttable()
    tab.header(["ID","Filename","Tags"])
    tab.set_cols_dtype(["i","t","t"])
    tab.set_cols_width([3,60,20])
    tab.set_cols_align(["r","l","l"])
    tab.set_deco(tab.HEADER | tab.VLINES)

    for doc in documents:
        row = [doc.id, doc.filename, doc.tags]
        tab.add_row(row)

    print(tab.draw())


def create_db():
    print("creating")
    Base.metadata.create_all(engine)
    print("done")

def add_tag(tagname):
    new_tag = Tag(value=tagname)
    session.add(new_tag)
    session.commit()

@clidms.command("open")
@click.argument("document_id")
def open_file(document_id):
    document = session.query(Document).filter_by(id=document_id).one()
    filepath = os.path.join(config.DOCUMENT_PATH, document.filename)
    print("Opening '{}'".format(filepath))
    subprocess.call(["xdg-open", filepath])



@clidms.command("tag")
@click.argument("documents")
@click.argument("tags")
def add_tag(documents, tags):
    documents = documents.split(",")
    tags = tags.split(",")

    for document_id in documents:
        try:
            document = session.query(Document).filter_by(id=document_id).one()
        except:
            logging.critical("No docment with this ID!")
            continue

        for tag_value in tags:
            try:
                tag = session.query(Tag).filter_by(value=tag_value).one()
            except:
                tag = Tag(value=tag_value)
                session.add(tag)
                session.commit()

            document.tags.append(tag)
            print("Added '{}' to '{}'".format(tag_value, document.filename))
            session.commit()

@clidms.command("find")
@click.option('--tag', '-t')
@click.option('--name', '-n')
def find(tag, name):
    query = session.query(Document)
    if name:
        query = query.filter(Document.filename.like('%{}%'.format(name)))
    if tag:
        query = query.filter(Document.tags.any(Tag.value.in_([tag])))
    
    results = query.all()
    if len(results) == 0:
        print("No documents matched your search")
    else:
        print_table(results)


if __name__ == '__main__':
    clidms()
