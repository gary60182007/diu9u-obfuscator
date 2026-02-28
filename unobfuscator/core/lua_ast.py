from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Any, Union


@dataclass
class SourceLocation:
    line: int = 0
    column: int = 0
    end_line: int = 0
    end_column: int = 0


class Node:
    loc: Optional[SourceLocation] = None

    def children(self) -> List[Node]:
        return []


# --------------- Expressions ---------------

class Expr(Node):
    pass


@dataclass
class Nil(Expr):
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Bool(Expr):
    value: bool = False
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Number(Expr):
    value: Union[int, float] = 0
    raw: str = ""
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class String(Expr):
    value: str = ""
    raw: str = ""
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Vararg(Expr):
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Name(Expr):
    name: str = ""
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class BinOp(Expr):
    op: str = ""
    left: Expr = None
    right: Expr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.left:
            r.append(self.left)
        if self.right:
            r.append(self.right)
        return r


@dataclass
class UnOp(Expr):
    op: str = ""
    operand: Expr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        return [self.operand] if self.operand else []


@dataclass
class Index(Expr):
    table: Expr = None
    key: Expr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.table:
            r.append(self.table)
        if self.key:
            r.append(self.key)
        return r


@dataclass
class Field(Expr):
    table: Expr = None
    name: str = ""
    loc: Optional[SourceLocation] = None

    def children(self):
        return [self.table] if self.table else []


@dataclass
class MethodCall(Expr):
    object: Expr = None
    method: str = ""
    args: List[Expr] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.object:
            r.append(self.object)
        r.extend(self.args)
        return r


@dataclass
class Call(Expr):
    func: Expr = None
    args: List[Expr] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.func:
            r.append(self.func)
        r.extend(self.args)
        return r


@dataclass
class TableConstructor(Expr):
    fields: List[TableField] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        return list(self.fields)


@dataclass
class TableField(Node):
    key: Optional[Expr] = None
    value: Expr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.key:
            r.append(self.key)
        if self.value:
            r.append(self.value)
        return r


@dataclass
class FunctionExpr(Expr):
    params: List[str] = field(default_factory=list)
    has_vararg: bool = False
    body: Block = None
    loc: Optional[SourceLocation] = None

    def children(self):
        return [self.body] if self.body else []


@dataclass
class Concat(Expr):
    values: List[Expr] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        return list(self.values)


# --------------- Statements ---------------

class Stmt(Node):
    pass


@dataclass
class Block(Node):
    stmts: List[Stmt] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        return list(self.stmts)


@dataclass
class Assign(Stmt):
    targets: List[Expr] = field(default_factory=list)
    values: List[Expr] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        return list(self.targets) + list(self.values)


@dataclass
class LocalAssign(Stmt):
    names: List[str] = field(default_factory=list)
    attribs: List[Optional[str]] = field(default_factory=list)
    values: List[Expr] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        return list(self.values)


@dataclass
class Do(Stmt):
    body: Block = None
    loc: Optional[SourceLocation] = None

    def children(self):
        return [self.body] if self.body else []


@dataclass
class While(Stmt):
    condition: Expr = None
    body: Block = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.condition:
            r.append(self.condition)
        if self.body:
            r.append(self.body)
        return r


@dataclass
class Repeat(Stmt):
    body: Block = None
    condition: Expr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.body:
            r.append(self.body)
        if self.condition:
            r.append(self.condition)
        return r


@dataclass
class If(Stmt):
    tests: List[Expr] = field(default_factory=list)
    bodies: List[Block] = field(default_factory=list)
    else_body: Optional[Block] = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = list(self.tests) + list(self.bodies)
        if self.else_body:
            r.append(self.else_body)
        return r


@dataclass
class ForNumeric(Stmt):
    name: str = ""
    start: Expr = None
    stop: Expr = None
    step: Optional[Expr] = None
    body: Block = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.start:
            r.append(self.start)
        if self.stop:
            r.append(self.stop)
        if self.step:
            r.append(self.step)
        if self.body:
            r.append(self.body)
        return r


@dataclass
class ForGeneric(Stmt):
    names: List[str] = field(default_factory=list)
    iterators: List[Expr] = field(default_factory=list)
    body: Block = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = list(self.iterators)
        if self.body:
            r.append(self.body)
        return r


@dataclass
class Return(Stmt):
    values: List[Expr] = field(default_factory=list)
    loc: Optional[SourceLocation] = None

    def children(self):
        return list(self.values)


@dataclass
class Break(Stmt):
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Continue(Stmt):
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Label(Stmt):
    name: str = ""
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class Goto(Stmt):
    name: str = ""
    loc: Optional[SourceLocation] = None

    def children(self):
        return []


@dataclass
class ExprStmt(Stmt):
    expr: Expr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        return [self.expr] if self.expr else []


@dataclass
class FunctionDecl(Stmt):
    name: Expr = None
    is_local: bool = False
    func: FunctionExpr = None
    loc: Optional[SourceLocation] = None

    def children(self):
        r = []
        if self.name:
            r.append(self.name)
        if self.func:
            r.append(self.func)
        return r


# --------------- Visitor / Transformer ---------------

class ASTVisitor:
    def visit(self, node: Node):
        method = 'visit_' + type(node).__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: Node):
        for child in node.children():
            self.visit(child)


class ASTTransformer:
    def transform(self, node: Node) -> Node:
        method = 'transform_' + type(node).__name__
        transformer = getattr(self, method, self.generic_transform)
        return transformer(node)

    def generic_transform(self, node: Node) -> Node:
        if isinstance(node, Block):
            node.stmts = [self.transform(s) for s in node.stmts]
        elif isinstance(node, Assign):
            node.targets = [self.transform(t) for t in node.targets]
            node.values = [self.transform(v) for v in node.values]
        elif isinstance(node, LocalAssign):
            node.values = [self.transform(v) for v in node.values]
        elif isinstance(node, Do):
            if node.body:
                node.body = self.transform(node.body)
        elif isinstance(node, While):
            if node.condition:
                node.condition = self.transform(node.condition)
            if node.body:
                node.body = self.transform(node.body)
        elif isinstance(node, Repeat):
            if node.body:
                node.body = self.transform(node.body)
            if node.condition:
                node.condition = self.transform(node.condition)
        elif isinstance(node, If):
            node.tests = [self.transform(t) for t in node.tests]
            node.bodies = [self.transform(b) for b in node.bodies]
            if node.else_body:
                node.else_body = self.transform(node.else_body)
        elif isinstance(node, ForNumeric):
            if node.start:
                node.start = self.transform(node.start)
            if node.stop:
                node.stop = self.transform(node.stop)
            if node.step:
                node.step = self.transform(node.step)
            if node.body:
                node.body = self.transform(node.body)
        elif isinstance(node, ForGeneric):
            node.iterators = [self.transform(i) for i in node.iterators]
            if node.body:
                node.body = self.transform(node.body)
        elif isinstance(node, Return):
            node.values = [self.transform(v) for v in node.values]
        elif isinstance(node, ExprStmt):
            if node.expr:
                node.expr = self.transform(node.expr)
        elif isinstance(node, FunctionDecl):
            if node.func:
                node.func = self.transform(node.func)
        elif isinstance(node, FunctionExpr):
            if node.body:
                node.body = self.transform(node.body)
        elif isinstance(node, BinOp):
            if node.left:
                node.left = self.transform(node.left)
            if node.right:
                node.right = self.transform(node.right)
        elif isinstance(node, UnOp):
            if node.operand:
                node.operand = self.transform(node.operand)
        elif isinstance(node, Call):
            if node.func:
                node.func = self.transform(node.func)
            node.args = [self.transform(a) for a in node.args]
        elif isinstance(node, MethodCall):
            if node.object:
                node.object = self.transform(node.object)
            node.args = [self.transform(a) for a in node.args]
        elif isinstance(node, Index):
            if node.table:
                node.table = self.transform(node.table)
            if node.key:
                node.key = self.transform(node.key)
        elif isinstance(node, Field):
            if node.table:
                node.table = self.transform(node.table)
        elif isinstance(node, TableConstructor):
            node.fields = [self.transform(f) for f in node.fields]
        elif isinstance(node, TableField):
            if node.key:
                node.key = self.transform(node.key)
            if node.value:
                node.value = self.transform(node.value)
        elif isinstance(node, Concat):
            node.values = [self.transform(v) for v in node.values]
        return node


def walk(node: Node):
    yield node
    for child in node.children():
        yield from walk(child)
