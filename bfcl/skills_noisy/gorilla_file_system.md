---
description: Tool reference for GorillaFileSystem — available file operations and their usage
when-to-use: When starting any file system task involving GorillaFileSystem tools — call this before your first tool call to check available operations and their exact parameters
---

# GorillaFileSystem Tool Reference

Available tools (18 total):

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `pwd` | Print current working directory | — |
| `ls` | List directory contents | `a` (bool): include hidden files |
| `cd` | Change directory | `folder` (str): **one level at a time**, not a full path |
| `mkdir` | Create directory at current location | `dir_name` (str) |
| `touch` | Create empty file | `file_name` (str) |
| `cat` | Print file contents | `file_name` (str) |
| `echo` | Write text to file | `content` (str), `file_name` (str, optional) |
| `cp` | Copy file | `source` (str), `destination` (str): both local to current dir |
| `mv` | Move or rename file | `source` (str), `destination` (str): both local to current dir, destination cannot be a path |
| `rm` | Remove file | `file_name` (str) |
| `rmdir` | Remove empty directory | `dir_name` (str) |
| `grep` | Search pattern in file | `file_name` (str), `pattern` (str) |
| `find` | Find files by name | `path` (str, optional), `name` (str, optional) |
| `sort` | Sort file lines alphabetically | `file_name` (str) |
| `diff` | Compare two files line by line | `file_name1` (str), `file_name2` (str) |
| `tail` | Show last N lines | `file_name` (str), `lines` (int, default 10) |
| `wc` | Count words or lines | `file_name` (str), `mode` (str: 'word'/'line') |
| `du` | Show directory disk usage | `human_readable` (bool) |

## Important Rules

- **No `head` tool**: Use `cat` to read full file or `tail` for last N lines.
- **No `chmod`, `chown`, `ln`**: Permission and link operations are not supported.
- **No `zip`/`tar`**: Compression tools are not available.
- **No `cut`/`awk`/`sed`**: Text processing pipelines are not supported.
- **`cd` takes one folder at a time**: Cannot use paths like `cd folder1/folder2`.
- **`mkdir` only at current directory**: Cannot create nested directories in one call.

## Missing Tool Behavior

If the user requests an operation not in the table above, **do not call any tool**. Respond that the required tool is not available in the current GorillaFileSystem.
