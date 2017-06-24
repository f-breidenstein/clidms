#! /usr/bin/env python3
import os
import sys
import logging
import click
from sqlalchemy import *
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import texttable as tt


Base = declarative_base()

association_table = Table('association', Base.metadata,
    Column('document_id', Integer, ForeignKey('Document.id')),
    Column('tag_id', Integer, ForeignKey('Tag.id'))
)

class Document(Base):
    __tablename__ = "Document"
    id = Column(Integer, primary_key=True)
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
    try:
        session.query(Document).one()
    except:
        print("There is no database. Creating a new one")
        create_db()


    files = os.listdir(config.DOCUMENT_PATH)
    supported_files = [f for f in files if f.split(".")[-1] in config.SUPPORTED_FILETYPES]
    print("Found {} files to index".format(len(supported_files)))
    for f in  supported_files:
        new_doc = Document(filename=f)
        session.add(new_doc)
    session.commit()

@clidms.command("list")
def list_documents():
    print_table(session.query(Document).all())


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
    Base.metadata.create_all(engine)

def add_tag(tagname):
    new_tag = Tag(value=tagname)
    session.add(new_tag)
    session.commit()
    print("Tag '{}' added".format(tagname))

@clidms.command("tag")
@click.argument("document_id")
@click.argument("tags")
def add_tag(document_id, tags):
    tags = tags.split(",")
    try:
        document = session.query(Document).filter_by(id=document_id).one()
    except:
        print("No docment with this ID!")
        return

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
    print_table(results)
    


if __name__ == '__main__':
    clidms()