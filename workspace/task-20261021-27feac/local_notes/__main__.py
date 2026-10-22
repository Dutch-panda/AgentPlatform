"""JSON argparse interface. Expected errors only are translated to stderr."""
import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import sys
from peewee import IntegrityError, OperationalError, DatabaseError
from . import Store, StoreError


def parser():
    p = argparse.ArgumentParser(description='Illustrative offline local notes')
    p.add_argument('--db', type=Path, default=Path('data/notes.sqlite3'))
    sub = p.add_subparsers(dest='entity', required=True)
    sub.add_parser('init')
    for entity, actions in [('notebook', ['add', 'list', 'get', 'rename', 'delete']),
                            ('note', ['add', 'list', 'get', 'update', 'delete'])]:
        group = sub.add_parser(entity).add_subparsers(dest='action', required=True)
        for action in actions:
            c = group.add_parser(action)
            if action in ('get', 'rename', 'update', 'delete'):
                c.add_argument('id', type=int)
            if entity == 'notebook' and action in ('add', 'rename'):
                c.add_argument('name')
            if entity == 'note':
                if action in ('add', 'list'):
                    c.add_argument('--notebook-id', type=int, required=True)
                if action == 'add':
                    c.add_argument('--title', required=True)
                    c.add_argument('--body', default='')
                if action == 'update':
                    c.add_argument('--notebook-id', type=int)
                    c.add_argument('--title')
                    c.add_argument('--body')
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.entity == 'note' and args.action == 'update' and all(
            getattr(args, f) is None for f in ('title', 'body', 'notebook_id')):
        p.error('note update requires --title, --body or --notebook-id')
    try:
        # Only init creates parent directories or a new database file.
        if args.entity == 'init':
            args.db.parent.mkdir(parents=True, exist_ok=True)
        elif not args.db.is_file():
            raise StoreError('database does not exist; run init first')
        with Store(args.db) as s:
            if args.entity == 'init':
                s.initialize()
                result = {'schema_version': 1}
            else:
                s.require_schema()
                a, e = args.action, args.entity
                if e == 'notebook':
                    if a == 'add': result = s.create_notebook(args.name)
                    elif a == 'list': result = s.list_notebooks()
                    elif a == 'get': result = s.get_notebook(args.id)
                    elif a == 'rename': result = s.rename_notebook(args.id, args.name)
                    else: result = s.delete_notebook(args.id)
                else:
                    if a == 'add': result = s.create_note(args.notebook_id, args.title, args.body)
                    elif a == 'list': result = s.list_notes(args.notebook_id)
                    elif a == 'get': result = s.get_note(args.id)
                    elif a == 'update': result = s.update_note(args.id, title=args.title,
                                                   body=args.body, notebook_id=args.notebook_id)
                    else: result = s.delete_note(args.id)
        def serialize(value):
            return asdict(value) if is_dataclass(value) else value
        print(json.dumps(result, default=serialize, ensure_ascii=False, sort_keys=True))
        return 0
    except IntegrityError as exc:
        print(f'constraint error: {exc}', file=sys.stderr)
        return 3
    except (StoreError, OperationalError, DatabaseError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
