#!/usr/bin/env python3
"""nt: simple note + todo helper."""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE = Path(os.environ.get("NT_HOME", SCRIPT_DIR / ".nt"))
NOTE_DIR_NAME = "notes"
TODOS_FILE_NAME = "todos.json"
DATE_FORMAT = "%d-%m-%Y"


@dataclass
class Todo:
    text: str
    tags: List[str]
    created: str  # yyyy-mm-dd
    status: str = "open"
    completed: Optional[str] = None  # yyyy-mm-dd when done


class NTApp:
    def __init__(self, base_dir: Path = DEFAULT_BASE) -> None:
        self.base_dir = base_dir
        self.notes_dir = self.base_dir / NOTE_DIR_NAME
        self.todos_file = self.base_dir / TODOS_FILE_NAME
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        self.todos_file.parent.mkdir(parents=True, exist_ok=True)

    def note_path_for(self, target: date) -> Path:
        year_dir = self.notes_dir / f"{target.year:04d}"
        month_dir = year_dir / f"{target.month:02d}"
        month_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{target.strftime(DATE_FORMAT)}.md"
        return month_dir / filename

    def ensure_note_file(self, target: date) -> Path:
        note_path = self.note_path_for(target)
        if not note_path.exists():
            header = [
                f"# {target.strftime(DATE_FORMAT)}",
                "",
                "## Todos",
                "",
                "## Notes",
                "",
            ]
            note_path.write_text("\n".join(header))
        return note_path

    # ------------- todos -------------
    def load_todos(self) -> List[Todo]:
        if not self.todos_file.exists():
            return []
        with self.todos_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [Todo(**item) for item in data]

    def save_todos(self, todos: List[Todo]) -> None:
        with self.todos_file.open("w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in todos], f, indent=2)

    def add_todo(self, text: str, tags: List[str], target_date: date) -> None:
        todo = Todo(
            text=text,
            tags=sorted(set(tags)),
            created=target_date.isoformat(),
        )
        todos = self.load_todos()
        todos.append(todo)
        self.save_todos(todos)

        note_path = self.ensure_note_file(target_date)
        tag_str = " ".join(f"#{t}" for t in todo.tags) if todo.tags else ""
        line = f"- [ ] {todo.text}"
        if tag_str:
            line += f" {tag_str}"
        self.append_to_section(note_path, "## Todos", line)
        print(f"Added todo -> {todo.text}")

    def update_todo_status(self, index: int, status: str) -> None:
        todos = self.load_todos()
        if not (1 <= index <= len(todos)):
            raise SystemExit(f"Todo #{index} does not exist.")
        todo = todos[index - 1]
        if todo.status == status:
            print(f"Todo #{index} already {status}.")
            return
        todo.status = status
        todo.completed = date.today().isoformat() if status == "done" else None
        self.save_todos(todos)
        print(f"Updated todo #{index} -> {status}: {todo.text}")

    def list_todos(self, status_filter: str = "all") -> None:
        todos = self.load_todos()
        if status_filter != "all":
            todos = [t for t in todos if t.status == status_filter]
        if not todos:
            print("No todos recorded.")
            return
        for idx, todo in enumerate(todos, start=1):
            tag_str = ", ".join(todo.tags) if todo.tags else "no tags"
            status_label = todo.status
            if todo.status == "done" and todo.completed:
                status_label = f"done @ {todo.completed}"
            print(f"{idx}. {todo.created} :: {todo.text} [{tag_str}] ({status_label})")

    # ------------- notes -------------
    def quick_note(self, message: str, tags: List[str], target_date: date) -> None:
        note_path = self.ensure_note_file(target_date)
        timestamp = datetime.now().strftime("%H:%M")
        tag_str = " ".join(f"#{t}" for t in sorted(set(tags))) if tags else ""
        line = f"- [{timestamp}] {message}"
        if tag_str:
            line += f" {tag_str}"
        self.append_to_section(note_path, "## Notes", line)
        print(f"Logged note -> {message}")

    def append_to_section(self, note_path: Path, heading: str, line: str) -> None:
        text = note_path.read_text(encoding="utf-8").rstrip("\n")
        lines = text.split("\n")
        if heading not in lines:
            lines.extend(["", heading])
        section_start = lines.index(heading)
        insert_at = len(lines)
        for i in range(section_start + 1, len(lines)):
            if lines[i].startswith("## "):
                insert_at = i
                break
        if insert_at > section_start + 1 and lines[insert_at - 1].strip():
            lines.insert(insert_at, "")
            insert_at += 1
        lines.insert(insert_at, line)
        note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ------------- open -------------
    def open_note(self, target_date: date) -> None:
        note_path = self.ensure_note_file(target_date)
        editor = os.environ.get("EDITOR") or "nano"
        try:
            subprocess.run([editor, str(note_path)], check=True)
        except FileNotFoundError:
            print(f"Editor {editor!r} not found. Set $EDITOR to your preferred editor.")
        except subprocess.CalledProcessError as exc:
            print(f"Editor exited with status {exc.returncode}")


def parse_date(value: Optional[str]) -> date:
    if value is None:
        return date.today()
    for fmt in ("%Y-%m-%d", DATE_FORMAT):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise SystemExit(f"Could not parse date {value!r}; use YYYY-MM-DD or DD-MM-YYYY.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="nt: simple daily notes + todo helper",
        usage="nt [todo|list|open|note|<tag> ...]",
    )
    sub = parser.add_subparsers(dest="command")

    todo_p = sub.add_parser("todo", help="add a todo to today's note")
    todo_p.add_argument("text", help="todo text")
    todo_p.add_argument(
        "-t", "--tag", action="append", dest="tags", default=[], help="tag"
    )
    todo_p.add_argument("--date", help="target date (YYYY-MM-DD or DD-MM-YYYY)")

    list_p = sub.add_parser("list", help="list all todos")
    list_p.add_argument(
        "--status",
        choices=["open", "done", "all"],
        default="all",
        help="filter by status (default: all)",
    )
    list_p.set_defaults(command="list")

    done_p = sub.add_parser("done", help="mark a todo as done")
    done_p.add_argument("index", type=int, help="todo number from `nt list`")

    reopen_p = sub.add_parser("reopen", help="move a completed todo back to open")
    reopen_p.add_argument("index", type=int, help="todo number from `nt list`")

    open_p = sub.add_parser(
        "open", help="open a daily note in $EDITOR (defaults to today)"
    )
    open_p.add_argument(
        "date", nargs="?", help="target date (YYYY-MM-DD or DD-MM-YYYY)"
    )

    note_p = sub.add_parser("note", help="add a quick note with tags")
    note_p.add_argument("message", help="note text")
    note_p.add_argument(
        "-t", "--tag", action="append", dest="tags", default=[], help="tag"
    )
    note_p.add_argument("--date", help="target date (YYYY-MM-DD or DD-MM-YYYY)")

    return parser


def maybe_quick_note_from_args(argv: List[str]) -> Optional[argparse.Namespace]:
    known = {"todo", "list", "open", "note", "done", "reopen", "-h", "--help"}
    if not argv or argv[0] in known:
        return None
    if len(argv) < 2:
        raise SystemExit('Usage: nt <tag...> "your message"')
    message = argv[-1]
    tags = argv[:-1]
    ns = argparse.Namespace(command="note", message=message, tags=tags, date=None)
    return ns


def main(argv: List[str]) -> None:
    app = NTApp()
    quick_note_ns = maybe_quick_note_from_args(argv)
    if quick_note_ns:
        args = quick_note_ns
    else:
        parser = build_parser()
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return

    if args.command == "todo":
        app.add_todo(args.text, args.tags, parse_date(args.date))
    elif args.command == "list":
        app.list_todos(args.status)
    elif args.command == "done":
        app.update_todo_status(args.index, "done")
    elif args.command == "reopen":
        app.update_todo_status(args.index, "open")
    elif args.command == "open":
        app.open_note(parse_date(args.date if hasattr(args, "date") else None))
    elif args.command == "note":
        app.quick_note(args.message, args.tags, parse_date(getattr(args, "date", None)))
    else:
        raise SystemExit(f"Unknown command {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
