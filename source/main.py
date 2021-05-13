from typing import List

import sys
from ast import (Assign, AsyncFunctionDef, ClassDef, ExceptHandler, Expr, For, FunctionDef, Import, ImportFrom, Module,
                 Name, Try, alias, arg, arguments, parse, With, AsyncWith, withitem, AsyncFor)
from dataclasses import dataclass
from os import path, walk

import re

from crayons import red
from rope.base.project import Project
from rope.refactor.rename import Rename


@dataclass
class Ident:
    name: str
    line: int
    col: int

@dataclass
class Span:
    name: str
    pos: int

flatten = lambda L: sum(L, [])

def _names(ast) -> List[Ident]:
    if isinstance(ast, arguments):
        return flatten([_names(arg) for arg in ast.args])
    if isinstance(ast, arg):
        return [Ident(ast.arg, ast.lineno, ast.col_offset)]
    if isinstance(ast, Name):
        return [Ident(ast.id, ast.lineno, ast.col_offset)]
    if isinstance(ast, Assign):
        return flatten([_names(x) for x in ast.targets])
    if isinstance(ast, FunctionDef):
        return flatten([_names(x) for x in ast.body]) + _names(ast.args) + [Ident(ast.name, ast.lineno, ast.col_offset + 4)]
    if isinstance(ast, AsyncFunctionDef):
        return flatten([_names(x) for x in ast.body]) + _names(ast.args) + [Ident(ast.name, ast.lineno, ast.col_offset + 10)]
    if isinstance(ast, ClassDef):
        return flatten([_names(x) for x in ast.body]) + [Ident(ast.name, ast.lineno, ast.col_offset + 6)]
    if isinstance(ast, (AsyncFor, For, Module, ExceptHandler)):
        return flatten([_names(x) for x in ast.body])
    if isinstance(ast, Try):
        return flatten([_names(x) for x in ast.body]) + flatten([_names(x) for x in ast.handlers])
    # if isinstance(ast, withitem):
    #     pass
    if isinstance(ast, (With, AsyncWith)):
        return flatten([_names(x) for x in ast.body])# + return flatten([_names(x) for x in ast.items])
    # if isinstance(ast, alias):
    #     if alias_ := ast.asname:
    #         return [Ident(f"{ast.name} as {alias_}", ast.lineno, ast.col + len(ast.name))]
    #     else:
    #         return []
    # if isinstance(ast, ImportFrom):
    #     return flatten([_names(x) for x in ast.names])
    print("skip: ", ast)
    return []

def symbols(path_: str) -> "Generator":
    with open(path_) as file:
        all_symbols = [span.name for span in get_all_symbols(file.read())]
    
    while True:
        with open(path_) as file:
            symbols_ = get_all_symbols(file.read())
        try:
            span = next(symbol for symbol in symbols_ if symbol.name in all_symbols)
            all_symbols.remove(span.name)
            yield span
        except StopIteration:
            return
            

def get_all_symbols(text: str) -> List[Span]:
    ast_ = parse(text)

    lines = [len(line) for line in text.splitlines(True)]

    skip = set()
    out = []
    for ident in _names(ast_):
        if not ident.name in skip:
            skip.add(ident.name)
            offset = sum(lines[:ident.line - 1]) + ident.col
            span = Span(ident.name, offset)
            out.append(span)

    return out

def replace(s: str, pos: int, sub: str) -> str:
    return s[:pos] + sub + s[pos + len(s) + 1:]

alphabet = "abcdefghijklmnopqrstuvwxyz"

def increment_name(name: str, pos: int) -> str:
    idx = alphabet.index(name[pos])
    if idx == len(alphabet) - 1:
        name = replace(name, pos, alphabet[0])
        if pos*-1 == len(name):
            name = alphabet[0] + name
            return name
        return increment_name(name, pos - 1)
    else:
        return replace(name, pos, alphabet[idx + 1])

python_keywords = ["in", "as", "not"]

def next_name(names: List[str]) -> str:
    if len(names) == 0:
        new = alphabet[0]
        names.append(new)
        return new
    
    new = increment_name(names[-1], -1)
    names.append(new)
    if new in python_keywords:
        return next_name(names)
    else:
        return new

# def refactor_imports(proj, res, path_, names):
#     with open(path_) as file:
#         content = file.read()
#     ast_ = [x for x in parse(content) is isinstance(x, Import)]
#     re = Restructure(proj, "")

PYDOC_PATTERN_SEMICOL = re.compile(r'(?<=:)\s+""".+"""')
PYDOC_PATTERN_MODULE = re.compile(r'^""".+"""')

def remove_pydoc(path_):
    """Let's be honest, nobody reads it anyway!"""
    with open(path_) as file:
        content = file.read()
    content = re.sub(PYDOC_PATTERN_SEMICOL, '', content)
    content = re.sub(PYDOC_PATTERN_MODULE, '', content)
    with open(path_, 'w') as file:
        file.write(content)

def process_file(proj, res, path_, names):
    for span in symbols(path_):
        print(span)
        name = next_name(names)
        print(f"[{span.name} @ {span.pos}] -> {name}")
        try:
            re = Rename(proj, res, span.pos)
        except Exception as e:
            print(f"PROBLEM RENAMING: {e}")
            continue
        ch = re.get_changes(name)
        proj.do(ch)

    remove_pydoc(path_)
    
    re = Rename(proj, res)
    new = next_name(names)
    print(f"Renaming module [{path.split(path_)[1]}] to [{new}]")
    ch = re.get_changes(new)
    proj.do(ch)
    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} [{red('path-to-project-root')}]")
        sys.exit(1)
    
    folder = sys.argv[1]

    proj = Project(folder)

    names = []

    for root, dirs, files in walk(folder):
        root_ = root.removeprefix(folder)
        for file in files:
            if not file.endswith(".py"):
                continue
            path_ = path.join(root_, file)
            realpath = path.join(root, file)
            process_file(proj, proj.get_resource(path_), realpath, names)