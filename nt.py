#!/usr/bin/env python3
"""nt: command line productivity system"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE = Path(os.environ.get("NT_HOME", Path.home() / ".nt"))
NOTE_DIR_NAME = "notes"
DATE_FORMAT = "%d-%m-%Y"


@dataclass
class Todo:
    text: str
    tags: list[str]
    created: str  # yyyy-mm-dd
    status: str = "open"
    due: str | None = None  # yyyy-mm-dd desired completion date
    completed: str | None = None  # yyyy-mm-dd when done


@dataclass
class TodoEntry:
    text: str
    tags: list[str]
    created: str
    file: Path
    line_no: int
    status: str = "open"
    due: str | None = None  # yyyy-mm-dd desired completion date
    completed: str | None = None  # yyyy-mm-dd when done


class NTApp:
    def __init__(self, base_dir: Path = DEFAULT_BASE) -> None:
        self.base_dir = base_dir
        self.notes_dir = self.base_dir / NOTE_DIR_NAME
        self.notes_dir.mkdir(parents=True, exist_ok=True)

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

    def parse_todo_line(
        self, line: str, file_path: Path, line_no: int
    ) -> TodoEntry | None:
        match = re.match(r"^- \[( |x)\] (?P<body>.+)$", line)
        if not match:
            return None
        body = match.group("body").strip()
        done_match = re.search(r"@done\s+(?P<date>\d{4}-\d{2}-\d{2})", body)
        completed = done_match.group("date") if done_match else None
        if completed:
            body = re.sub(r"\s*@done\s+\d{4}-\d{2}-\d{2}", "", body).strip()

        due_match = re.search(r"@due\s+(?P<date>\d{4}-\d{2}-\d{2})", body)
        due = due_match.group("date") if due_match else None
        if due:
            body = re.sub(r"\s*@due\s+\d{4}-\d{2}-\d{2}", "", body).strip()

        tags = re.findall(r"#([\w-]+)", body)
        text = re.sub(r"#([\w-]+)", "", body).strip()

        created_date = self.date_from_note_path(file_path)
        created = created_date.isoformat() if created_date else date.today().isoformat()

        status = "done" if match.group(1) == "x" else "open"

        return TodoEntry(
            text=text,
            tags=sorted(set(tags)),
            created=created,
            file=file_path,
            line_no=line_no,
            status=status,
            due=due,
            completed=completed,
        )

    def date_from_note_path(self, note_path: Path) -> date | None:
        try:
            return datetime.strptime(note_path.stem, DATE_FORMAT).date()
        except ValueError:
            return None

    def todo_matches_from_rg(self) -> list[TodoEntry]:
        if not self.notes_dir.exists():
            return []
        pattern = r"^- \[( |x)\] "
        cmd = [
            "rg",
            "--with-filename",
            "--line-number",
            "--no-heading",
            pattern,
            str(self.notes_dir),
        ]
        res = subprocess.run(cmd, check=False, capture_output=True, text=True)

        if res.returncode not in (0, 1):
            raise SystemExit(
                f"ripgrep failed with exit code {res.returncode}: {res.stderr.strip()}"
            )

        entries: list[TodoEntry] = []
        for line in res.stdout.splitlines():
            try:
                path_str, line_no_str, content = line.split(":", 2)
            except ValueError:
                continue
            todo = self.parse_todo_line(content, Path(path_str), int(line_no_str))
            if todo:
                entries.append(todo)
        return entries

    def load_todos(self) -> list[TodoEntry]:
        todos = self.todo_matches_from_rg()
        todos.sort(key=lambda t: (t.created, t.file.as_posix(), t.line_no))
        return todos

    def add_todo(
        self, text: str, tags: list[str], target_date: date, due_date: date | None
    ) -> None:
        todo = Todo(
            text=text,
            tags=sorted(set(tags)),
            created=target_date.isoformat(),
            due=due_date.isoformat() if due_date else None,
        )

        note_path = self.ensure_note_file(target_date)
        tag_str = " ".join(f"#{t}" for t in todo.tags) if todo.tags else ""
        line = f"- [ ] {todo.text}"
        if todo.due:
            line += f" @due {todo.due}"
        if tag_str:
            line += f" {tag_str}"
        self.append_to_section(note_path, "## Todos", line)
        print(f"added todo -> {todo.text}")

    def update_todo_status(self, index: int, status: str) -> None:
        todos = self.load_todos()
        if not (1 <= index <= len(todos)):
            raise SystemExit(f"todo #{index} does not exist.")
        todo = todos[index - 1]
        if todo.status == status:
            print(f"todo #{index} already {status}.")
            return

        lines = todo.file.read_text(encoding="utf-8").splitlines()
        try:
            original = lines[todo.line_no - 1]
        except IndexError:
            raise SystemExit(f"todo #{index} could not be updated (line missing).")

        if status == "done":
            updated = re.sub(r"^- \[( |x)\] ", "- [x] ", original, count=1)
            if "@done" not in updated:
                updated = updated.rstrip() + f" @done {date.today().isoformat()}"
            completed_date = date.today().isoformat()
        else:
            updated = re.sub(r"^- \[( |x)\] ", "- [ ] ", original, count=1)
            updated = re.sub(r"\s*@done\s+\d{4}-\d{2}-\d{2}", "", updated).rstrip()
            completed_date = None

        lines[todo.line_no - 1] = updated
        todo.file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        todo.status = status
        todo.completed = completed_date
        print(f"updated todo #{index} -> {status}: {todo.text}")

    def list_todos(self, status_filter: str = "all") -> None:
        todos = self.load_todos()
        if status_filter != "all":
            todos = [t for t in todos if t.status == status_filter]
        if not todos:
            print("no todos recorded.")
            return
        for idx, todo in enumerate(todos, start=1):
            tag_str = ", ".join(todo.tags) if todo.tags else "no tags"
            status_label = todo.status
            if todo.status == "done" and todo.completed:
                status_label = f"done @ {todo.completed}"
            labels = [status_label]
            if todo.due:
                labels.append(f"due {todo.due}")
            print(
                f"{idx}. {todo.created} :: {todo.text} [{tag_str}] ({'; '.join(labels)})"
            )

    def agenda(self, tags: list[str] | None = None) -> None:
        todos = []
        for idx, todo in enumerate(self.load_todos(), start=1):
            if todo.status != "open":
                continue
            if tags and not set(tags).issubset(set(todo.tags)):
                continue
            todos.append((idx, todo))
        if not todos:
            print("no open todos.")
            return

        by_date = {}
        for idx, todo in todos:
            key = todo.due or todo.created
            by_date.setdefault(key, []).append((idx, todo))

        for key in sorted(by_date.keys()):
            print(key)
            entries = sorted(
                by_date[key],
                key=lambda pair: (
                    pair[1].created,
                    pair[1].file.as_posix(),
                    pair[1].line_no,
                ),
            )
            for idx, todo in entries:
                tag_str = " ".join(f"#{t}" for t in todo.tags) if todo.tags else ""
                try:
                    rel = todo.file.relative_to(self.base_dir)
                except ValueError:
                    rel = todo.file
                location = f" @ {rel}:{todo.line_no}"
                line = f"  [{idx}] {todo.text}"
                if tag_str:
                    line += f" {tag_str}"
                if todo.due:
                    line += f" (due {todo.due})"
                line += location
                print(line)

    def quick_note(self, message: str, tags: list[str], target_date: date) -> None:
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

    def list_notes_fzf(self) -> None:
        if not self.notes_dir.exists():
            print("no notes recorded.")
            return
        note_files = []
        for path in self.notes_dir.rglob("*.md"):
            note_date = self.date_from_note_path(path)
            if note_date is None:
                continue
            note_files.append((note_date, path))
        if not note_files:
            print("no notes recorded.")
            return

        note_files.sort(key=lambda pair: pair[0], reverse=True)
        lines = []
        for note_date, path in note_files:
            try:
                rel = path.relative_to(self.base_dir)
            except ValueError:
                rel = path
            lines.append(f"{note_date.isoformat()}\t{rel}")

        cmd = ["fzf", "--multi", "--delimiter", "\t", "--with-nth", "1,2"]
        try:
            res = subprocess.run(
                cmd,
                input="\n".join(lines),
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            raise SystemExit("fzf not found. install fzf to use `nt notes`.")

        if res.returncode == 130:
            return
        if res.returncode != 0:
            raise SystemExit(
                f"fzf failed with exit code {res.returncode}: {res.stderr.strip()}"
            )
        if not res.stdout:
            return

        selected_paths: list[Path] = []
        for line in res.stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            path_str = parts[1]
            path = Path(path_str)
            if not path.is_absolute():
                path = self.base_dir / path
            selected_paths.append(path)

        if not selected_paths:
            return

        editor = os.environ.get("EDITOR") or "nano"
        try:
            subprocess.run([editor, *[str(p) for p in selected_paths]], check=True)
        except FileNotFoundError:
            print(f"editor {editor!r} not found. set $EDITOR to your preferred editor.")
        except subprocess.CalledProcessError as exc:
            print(f"editor exited with status {exc.returncode}")

    def open_note(self, target_date: date) -> None:
        note_path = self.ensure_note_file(target_date)
        editor = os.environ.get("EDITOR") or "nano"
        try:
            subprocess.run([editor, str(note_path)], check=True)
        except FileNotFoundError:
            print(f"editor {editor!r} not found. set $EDITOR to your preferred editor.")
        except subprocess.CalledProcessError as exc:
            print(f"editor exited with status {exc.returncode}")


def parse_date(value: str | None) -> date:
    if value is None:
        return date.today()
    for fmt in ("%Y-%m-%d", DATE_FORMAT):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise SystemExit(f"could not parse date {value!r}; use YYYY-MM-DD or DD-MM-YYYY.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="nt: command line productivity tool",
        usage="nt [todo|list|agenda|open|notes|note|<tag> ...]",
        epilog="notes are stored in $NT_HOME (default: $HOME/.nt)",
    )
    sub = parser.add_subparsers(dest="command")

    todo_p = sub.add_parser("todo", help="add a todo to today's note")
    todo_p.add_argument("text", help="todo text")
    todo_p.add_argument(
        "-t", "--tag", action="append", dest="tags", default=[], help="tag"
    )
    todo_p.add_argument("--date", help="target date (YYYY-MM-DD or DD-MM-YYYY)")
    todo_p.add_argument(
        "--due",
        help="desired completion date for the todo (YYYY-MM-DD or DD-MM-YYYY)",
    )

    list_p = sub.add_parser("list", help="list all todos")
    list_p.add_argument(
        "--status",
        choices=["open", "done", "all"],
        default="all",
        help="filter by status (default: all)",
    )
    list_p.set_defaults(command="list")

    agenda_p = sub.add_parser("agenda", help="agenda view grouped by date")
    agenda_p.add_argument(
        "-t",
        "--tag",
        action="append",
        dest="tags",
        default=[],
        help="filter agenda to todos containing this tag (can be repeated)",
    )
    agenda_p.set_defaults(command="agenda")

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

    notes_p = sub.add_parser("notes", help="pick daily notes via fzf")
    notes_p.set_defaults(command="notes")

    note_p = sub.add_parser("note", help="add a quick note with tags")
    note_p.add_argument("message", help="note text")
    note_p.add_argument(
        "-t", "--tag", action="append", dest="tags", default=[], help="tag"
    )
    note_p.add_argument("--date", help="target date (YYYY-MM-DD or DD-MM-YYYY)")

    return parser


def maybe_quick_note_from_args(argv: list[str]) -> argparse.Namespace | None:
    known = {
        "todo",
        "list",
        "agenda",
        "open",
        "notes",
        "note",
        "done",
        "reopen",
        "-h",
        "--help",
    }
    if not argv or argv[0] in known:
        return None
    if len(argv) < 2:
        raise SystemExit('usage: nt <tag...> "your message"')
    message = argv[-1]
    tags = argv[:-1]
    ns = argparse.Namespace(command="note", message=message, tags=tags, date=None)
    return ns


def main(argv: list[str]) -> None:
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
        app.add_todo(
            args.text,
            args.tags,
            parse_date(args.date),
            parse_date(args.due) if getattr(args, "due", None) else None,
        )
    elif args.command == "list":
        app.list_todos(args.status)
    elif args.command == "done":
        app.update_todo_status(args.index, "done")
    elif args.command == "reopen":
        app.update_todo_status(args.index, "open")
    elif args.command == "agenda":
        app.agenda(args.tags)
    elif args.command == "open":
        app.open_note(parse_date(args.date if hasattr(args, "date") else None))
    elif args.command == "notes":
        app.list_notes_fzf()
    elif args.command == "note":
        app.quick_note(args.message, args.tags, parse_date(getattr(args, "date", None)))
    else:
        raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
