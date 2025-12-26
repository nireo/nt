# nt: a small command line productivity tool

This repository contains a small script to handle daily notes and todos. It's editor-agnostic, since it uses `$EDITOR` to edit daily notes. It also supports adding quick notes with a command rather than opening an editor. It also automatically reads todos from daily notes similar to org mode.

## Dependencies

Some commands require external dependencies to make it work efficiently with many files, these are:
- `rg` ripgrep to quickly find todos
- `fzf` fuzzy picker for terminal to list all notes

## Usage

The notes are stored in `$HOME/.nt` and they're grouped by year.

```
$ nt

usage: nt [todo|list|agenda|open|notes|note|<tag> ...]

nt: command line productivity tool

positional arguments:
  {todo,list,agenda,done,reopen,open,notes,note}
    todo                add a todo to today's note
    list                list all todos
    agenda              agenda view grouped by date
    done                mark a todo as done
    reopen              move a completed todo back to open
    open                open a daily note in $EDITOR (defaults to today)
    notes               pick daily notes via fzf
    note                add a quick note with tags
```

