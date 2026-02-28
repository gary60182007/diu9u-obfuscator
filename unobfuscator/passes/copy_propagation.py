from __future__ import annotations
from typing import Dict, Set, List, Optional, Tuple
from ..core import lua_ast as ast


class CopyInfo:
    def __init__(self):
        self.copies: Dict[str, str] = {}
        self.write_counts: Dict[str, int] = {}
        self.read_counts: Dict[str, int] = {}

    def add_copy(self, dst: str, src: str):
        self.copies[dst] = src

    def add_write(self, name: str):
        self.write_counts[name] = self.write_counts.get(name, 0) + 1

    def add_read(self, name: str):
        self.read_counts[name] = self.read_counts.get(name, 0) + 1

    def resolve(self, name: str, max_depth: int = 20) -> str:
        visited = set()
        cur = name
        for _ in range(max_depth):
            if cur in visited:
                break
            visited.add(cur)
            if cur in self.copies:
                nxt = self.copies[cur]
                if self.write_counts.get(nxt, 0) <= 1:
                    cur = nxt
                else:
                    break
            else:
                break
        return cur

    def is_single_assign_copy(self, name: str) -> bool:
        return (name in self.copies and
                self.write_counts.get(name, 0) == 1 and
                self.write_counts.get(self.copies[name], 0) <= 1)


class CopyCollector(ast.ASTVisitor):
    def __init__(self):
        self.info = CopyInfo()

    def collect(self, tree: ast.Block):
        self._collect_writes(tree)
        self._collect_reads(tree)
        self._collect_copies(tree)

    def _collect_writes(self, node: ast.Node):
        if isinstance(node, ast.LocalAssign):
            for nm in node.names:
                self.info.add_write(nm)
            for v in node.values:
                self._collect_writes(v)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    self.info.add_write(tgt.name)
                self._collect_writes(tgt)
            for v in node.values:
                self._collect_writes(v)
        elif isinstance(node, ast.ForNumeric):
            self.info.add_write(node.name)
            self._collect_writes(node.start)
            self._collect_writes(node.stop)
            if node.step:
                self._collect_writes(node.step)
            self._collect_writes(node.body)
        elif isinstance(node, ast.ForGeneric):
            for nm in node.names:
                self.info.add_write(nm)
            for it in node.iterators:
                self._collect_writes(it)
            self._collect_writes(node.body)
        elif isinstance(node, ast.FunctionDecl):
            if node.is_local and isinstance(node.name, ast.Name):
                self.info.add_write(node.name.name)
            elif isinstance(node.name, ast.Name):
                self.info.add_write(node.name.name)
            if node.func:
                self._collect_writes(node.func.body)
        else:
            for child in node.children():
                self._collect_writes(child)

    def _collect_reads(self, node: ast.Node):
        if isinstance(node, ast.Name):
            self.info.add_read(node.name)
        if isinstance(node, ast.Assign):
            for v in node.values:
                self._collect_reads(v)
            for tgt in node.targets:
                if isinstance(tgt, (ast.Index, ast.Field)):
                    self._collect_reads(tgt)
            return
        for child in node.children():
            self._collect_reads(child)

    def _collect_copies(self, tree: ast.Block):
        for stmt in tree.stmts:
            if isinstance(stmt, ast.LocalAssign):
                if len(stmt.names) == 1 and len(stmt.values) == 1:
                    if isinstance(stmt.values[0], ast.Name):
                        self.info.add_copy(stmt.names[0], stmt.values[0].name)
            elif isinstance(stmt, ast.Assign):
                if len(stmt.targets) == 1 and len(stmt.values) == 1:
                    if isinstance(stmt.targets[0], ast.Name) and isinstance(stmt.values[0], ast.Name):
                        self.info.add_copy(stmt.targets[0].name, stmt.values[0].name)
            if isinstance(stmt, (ast.If, ast.While, ast.ForNumeric, ast.ForGeneric, ast.Do, ast.Repeat)):
                for child in stmt.children():
                    if isinstance(child, ast.Block):
                        self._collect_copies(child)
            if isinstance(stmt, ast.FunctionDecl) and stmt.func:
                self._collect_copies(stmt.func.body)


class CopyPropagator(ast.ASTTransformer):
    def __init__(self, info: CopyInfo):
        self.info = info
        self.changes = 0

    def propagate(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_Name(self, node: ast.Name) -> ast.Expr:
        resolved = self.info.resolve(node.name)
        if resolved != node.name:
            self.changes += 1
            return ast.Name(name=resolved, loc=node.loc)
        return node

    def transform_Assign(self, node: ast.Assign) -> ast.Stmt:
        new_values = [self.transform(v) for v in node.values]
        return ast.Assign(targets=node.targets, values=new_values, loc=node.loc)


class CopyEliminator(ast.ASTTransformer):
    def __init__(self, info: CopyInfo):
        self.info = info
        self.changes = 0

    def eliminate(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_Block(self, node: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in node.stmts:
            s = self.transform(stmt)
            if self._is_dead_copy(s):
                self.changes += 1
                continue
            new_stmts.append(s)
        return ast.Block(stmts=new_stmts, loc=node.loc)

    def _is_dead_copy(self, stmt: ast.Stmt) -> bool:
        if isinstance(stmt, ast.LocalAssign) and len(stmt.names) == 1 and len(stmt.values) == 1:
            nm = stmt.names[0]
            if isinstance(stmt.values[0], ast.Name) and self.info.is_single_assign_copy(nm):
                if self.info.read_counts.get(nm, 0) == 0:
                    return True
                resolved = self.info.resolve(nm)
                if resolved != nm and resolved != stmt.values[0].name:
                    return True
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and len(stmt.values) == 1:
            if isinstance(stmt.targets[0], ast.Name) and isinstance(stmt.values[0], ast.Name):
                if stmt.targets[0].name == stmt.values[0].name:
                    return True
        return False


def propagate_copies(tree: ast.Block, iterations: int = 5) -> ast.Block:
    for _ in range(iterations):
        cc = CopyCollector()
        cc.collect(tree)
        cp = CopyPropagator(cc.info)
        tree = cp.propagate(tree)
        ce = CopyEliminator(cc.info)
        tree = ce.eliminate(tree)
        if cp.changes == 0 and ce.changes == 0:
            break
    return tree
