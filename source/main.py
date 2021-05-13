from typing import List

from ast import parse, Name, Assign, Module, FunctionDef, arguments, arg, ClassDef, Expr, For, Try, ExceptHandler

from dataclasses import dataclass

from os import path, walk

from crayons import red

from rope.base.project import Project
from rope.refactor.rename import Rename

import sys

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
    if isinstance(ast, ClassDef):
        return flatten([_names(x) for x in ast.body]) + [Ident(ast.name, ast.lineno, ast.col_offset + 6)]
    if isinstance(ast, (For, Module, ExceptHandler)):
        return flatten([_names(x) for x in ast.body])
    if isinstance(ast, Try):
        return flatten([_names(x) for x in ast.body]) + flatten([_names(x) for x in ast.handlers])
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

def next_name(names: List[str]) -> str:
    if len(names) == 0:
        new = alphabet[0]
        names.append(new)
        return new
    
    new = increment_name(names[-1], -1)
    names.append(new)
    return new

def process_file(proj, res, path_, names):
    for span in symbols(path_):
        print(span)
        name = next_name(names)
        print(f"[{span.name} @ {span.pos}] -> {name}")
        re = Rename(proj, res, span.pos)
        ch = re.get_changes(name)
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