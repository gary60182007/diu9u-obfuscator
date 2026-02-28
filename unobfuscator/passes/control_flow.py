from __future__ import annotations
from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from ..core import lua_ast as ast
from ..core.cfg import CFG, BasicBlock, DominatorTree, build_cfg, compute_dominators


class RegionKind(Enum):
    BLOCK = auto()
    IF_THEN = auto()
    IF_THEN_ELSE = auto()
    WHILE_LOOP = auto()
    REPEAT_UNTIL = auto()
    NATURAL_LOOP = auto()
    SEQUENCE = auto()
    SWITCH = auto()


@dataclass
class Region:
    kind: RegionKind
    entry: int
    exits: Set[int] = field(default_factory=set)
    children: List[Region] = field(default_factory=list)
    blocks: Set[int] = field(default_factory=set)
    condition: Optional[ast.Expr] = None
    header: Optional[int] = None


class StructuralAnalyzer:
    def __init__(self, cfg: CFG, dom: DominatorTree):
        self.cfg = cfg
        self.dom = dom
        self.loops = dom.loops
        self.regions: List[Region] = []

    def analyze(self) -> List[Region]:
        self.regions = []
        self._identify_loops()
        self._identify_conditionals()
        return self.regions

    def _identify_loops(self):
        for header, back_edges in self.loops.items():
            body_blocks = set()
            for be in back_edges:
                body_blocks |= self._collect_loop_body(header, be)
            body_blocks.add(header)

            exits = set()
            for bid in body_blocks:
                bb = self.cfg.blocks[bid]
                for succ in bb.succs:
                    if succ not in body_blocks:
                        exits.add(succ)

            region = Region(
                kind=RegionKind.NATURAL_LOOP,
                entry=header,
                exits=exits,
                blocks=body_blocks,
                header=header,
            )
            self.regions.append(region)

    def _collect_loop_body(self, header: int, back_edge_src: int) -> Set[int]:
        body = {header, back_edge_src}
        worklist = [back_edge_src]
        while worklist:
            n = worklist.pop()
            bb = self.cfg.blocks.get(n)
            if bb is None:
                continue
            for pred in bb.preds:
                if pred not in body:
                    body.add(pred)
                    worklist.append(pred)
        return body

    def _identify_conditionals(self):
        for bid, bb in self.cfg.blocks.items():
            if len(bb.succs) == 2:
                then_id, else_id = list(bb.succs)[:2]
                then_bb = self.cfg.blocks.get(then_id)
                else_bb = self.cfg.blocks.get(else_id)
                if then_bb is None or else_bb is None:
                    continue

                common_succ = set(then_bb.succs) & set(else_bb.succs)
                if common_succ:
                    region = Region(
                        kind=RegionKind.IF_THEN_ELSE,
                        entry=bid,
                        exits=common_succ,
                        blocks={bid, then_id, else_id},
                    )
                    self.regions.append(region)
                elif set(bb.succs) & set(then_bb.succs):
                    join = set(bb.succs) & set(then_bb.succs)
                    if join:
                        region = Region(
                            kind=RegionKind.IF_THEN,
                            entry=bid,
                            exits=join,
                            blocks={bid, then_id},
                        )
                        self.regions.append(region)


class ControlFlowRestorer(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0

    def restore(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        tree = self._flatten_single_while_body(tree)
        tree = self._restore_dispatch_loops(tree)
        tree = self._simplify_state_machines(tree)
        tree = self._collapse_nested_ifs(tree)
        tree = self._remove_redundant_breaks(tree)
        return self.transform(tree)

    def _flatten_single_while_body(self, tree: ast.Block) -> ast.Block:
        if len(tree.stmts) == 1 and isinstance(tree.stmts[0], ast.While):
            w = tree.stmts[0]
            cv = _const_val(w.condition)
            if cv is not None and _truthy(cv):
                if self._is_dispatch_loop(w.body):
                    return tree
        return tree

    def _is_dispatch_loop(self, body: ast.Block) -> bool:
        if not body.stmts:
            return False
        for stmt in body.stmts:
            if isinstance(stmt, ast.If) and len(stmt.tests) >= 3:
                state_vars = set()
                for test in stmt.tests:
                    if isinstance(test, ast.BinOp) and test.op == '==':
                        if isinstance(test.left, ast.Name):
                            state_vars.add(test.left.name)
                if state_vars:
                    return True
        return False

    def _restore_dispatch_loops(self, tree: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in tree.stmts:
            if isinstance(stmt, ast.While):
                restored = self._try_restore_dispatch(stmt)
                if restored is not None:
                    new_stmts.extend(restored)
                    self.changes += 1
                    continue
            new_stmts.append(self._recursive_restore(stmt))
        return ast.Block(stmts=new_stmts, loc=tree.loc)

    def _try_restore_dispatch(self, stmt: ast.While) -> Optional[List[ast.Stmt]]:
        cv = _const_val(stmt.condition)
        if cv is None or not _truthy(cv):
            return None
        body = stmt.body
        state_var, transitions = self._analyze_state_machine(body)
        if state_var is None or len(transitions) < 2:
            return None
        ordered = self._topological_order(transitions)
        if ordered is None:
            return None
        result = []
        for state_id in ordered:
            if state_id in transitions:
                block = transitions[state_id]
                cleaned = self._remove_state_updates(block, state_var)
                result.extend(cleaned.stmts)
        return result if result else None

    def _analyze_state_machine(self, body: ast.Block) -> Tuple[Optional[str], Dict]:
        transitions: Dict[any, ast.Block] = {}
        state_var = None

        for stmt in body.stmts:
            if isinstance(stmt, ast.If):
                for i, test in enumerate(stmt.tests):
                    if isinstance(test, ast.BinOp) and test.op == '==' and isinstance(test.left, ast.Name):
                        if state_var is None:
                            state_var = test.left.name
                        elif state_var != test.left.name:
                            continue
                        key = _const_val(test.right)
                        if key is not None and i < len(stmt.bodies):
                            transitions[key] = stmt.bodies[i]

        return state_var, transitions

    def _topological_order(self, transitions: Dict) -> Optional[List]:
        keys = sorted(transitions.keys(), key=lambda k: k if isinstance(k, (int, float)) else 0)
        return keys

    def _remove_state_updates(self, block: ast.Block, state_var: str) -> ast.Block:
        new_stmts = []
        for stmt in block.stmts:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                if isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].name == state_var:
                    continue
            if isinstance(stmt, ast.LocalAssign) and len(stmt.names) == 1:
                if stmt.names[0] == state_var:
                    continue
            if isinstance(stmt, ast.Break):
                continue
            new_stmts.append(stmt)
        return ast.Block(stmts=new_stmts, loc=block.loc)

    def _simplify_state_machines(self, tree: ast.Block) -> ast.Block:
        return tree

    def _collapse_nested_ifs(self, tree: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in tree.stmts:
            s = self._collapse_if(stmt)
            new_stmts.append(s)
        return ast.Block(stmts=new_stmts, loc=tree.loc)

    def _collapse_if(self, stmt: ast.Stmt) -> ast.Stmt:
        if not isinstance(stmt, ast.If):
            return stmt
        if len(stmt.tests) == 1 and stmt.else_body and not stmt.else_body.stmts:
            return stmt

        if (len(stmt.tests) == 1 and stmt.else_body is None and
            len(stmt.bodies[0].stmts) == 1 and isinstance(stmt.bodies[0].stmts[0], ast.If)):
            inner = stmt.bodies[0].stmts[0]
            if len(inner.tests) == 1 and inner.else_body is None:
                merged_cond = ast.BinOp(
                    op='and',
                    left=stmt.tests[0],
                    right=inner.tests[0],
                    loc=stmt.loc,
                )
                self.changes += 1
                return ast.If(
                    tests=[merged_cond],
                    bodies=[inner.bodies[0]],
                    else_body=None,
                    loc=stmt.loc,
                )
        return stmt

    def _remove_redundant_breaks(self, tree: ast.Block) -> ast.Block:
        new_stmts = []
        for stmt in tree.stmts:
            if isinstance(stmt, ast.While):
                body = self._clean_breaks(stmt.body)
                new_stmts.append(ast.While(condition=stmt.condition, body=body, loc=stmt.loc))
            elif isinstance(stmt, ast.ForNumeric):
                body = self._clean_breaks(stmt.body)
                new_stmts.append(ast.ForNumeric(
                    name=stmt.name, start=stmt.start, stop=stmt.stop,
                    step=stmt.step, body=body, loc=stmt.loc,
                ))
            elif isinstance(stmt, ast.ForGeneric):
                body = self._clean_breaks(stmt.body)
                new_stmts.append(ast.ForGeneric(
                    names=stmt.names, iterators=stmt.iterators,
                    body=body, loc=stmt.loc,
                ))
            else:
                new_stmts.append(stmt)
        return ast.Block(stmts=new_stmts, loc=tree.loc)

    def _clean_breaks(self, body: ast.Block) -> ast.Block:
        if not body.stmts:
            return body
        last = body.stmts[-1]
        if isinstance(last, ast.If) and last.else_body:
            then_ends_break = self._ends_with_break(last.bodies[-1])
            else_ends_break = self._ends_with_break(last.else_body)
            if then_ends_break and else_ends_break:
                pass
        return body

    def _ends_with_break(self, body: ast.Block) -> bool:
        if not body.stmts:
            return False
        return isinstance(body.stmts[-1], ast.Break)

    def _recursive_restore(self, stmt: ast.Stmt) -> ast.Stmt:
        if isinstance(stmt, ast.If):
            new_bodies = [self._restore_dispatch_loops(b) if isinstance(b, ast.Block) else b for b in stmt.bodies]
            else_body = self._restore_dispatch_loops(stmt.else_body) if stmt.else_body else None
            return ast.If(tests=stmt.tests, bodies=new_bodies, else_body=else_body, loc=stmt.loc)
        if isinstance(stmt, ast.While):
            body = self._restore_dispatch_loops(stmt.body) if isinstance(stmt.body, ast.Block) else stmt.body
            return ast.While(condition=stmt.condition, body=body, loc=stmt.loc)
        if isinstance(stmt, ast.Do):
            body = self._restore_dispatch_loops(stmt.body) if isinstance(stmt.body, ast.Block) else stmt.body
            return ast.Do(body=body, loc=stmt.loc)
        if isinstance(stmt, ast.FunctionDecl) and stmt.func:
            body = self._restore_dispatch_loops(stmt.func.body) if isinstance(stmt.func.body, ast.Block) else stmt.func.body
            new_func = ast.FunctionExpr(
                params=stmt.func.params,
                has_vararg=stmt.func.has_vararg,
                body=body,
                loc=stmt.func.loc,
            )
            return ast.FunctionDecl(
                name=stmt.name, is_local=stmt.is_local, func=new_func, loc=stmt.loc,
            )
        return stmt


class WhileToForConverter(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0

    def convert(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        return self.transform(tree)

    def transform_Block(self, node: ast.Block) -> ast.Block:
        new_stmts = []
        i = 0
        while i < len(node.stmts):
            stmt = node.stmts[i]
            if (i + 1 < len(node.stmts) and isinstance(stmt, ast.LocalAssign) and
                isinstance(node.stmts[i + 1], ast.While)):
                result = self._try_convert(stmt, node.stmts[i + 1])
                if result is not None:
                    new_stmts.append(self.transform(result))
                    self.changes += 1
                    i += 2
                    continue
            new_stmts.append(self.transform(stmt))
            i += 1
        return ast.Block(stmts=new_stmts, loc=node.loc)

    def _try_convert(self, init: ast.LocalAssign, loop: ast.While) -> Optional[ast.ForNumeric]:
        if len(init.names) != 1 or len(init.values) != 1:
            return None
        var_name = init.names[0]
        start_val = init.values[0]
        if not isinstance(start_val, ast.Number):
            return None

        cond = loop.condition
        if not isinstance(cond, ast.BinOp) or cond.op not in ('<=', '<', '>=', '>'):
            return None
        if not isinstance(cond.left, ast.Name) or cond.left.name != var_name:
            return None
        stop_val = cond.right

        body = loop.body
        if not body.stmts:
            return None
        last = body.stmts[-1]
        step_val = self._extract_increment(last, var_name)
        if step_val is None:
            return None

        new_body_stmts = body.stmts[:-1]
        actual_stop = stop_val

        if cond.op == '<':
            if isinstance(stop_val, ast.Number):
                actual_stop = ast.Number(value=stop_val.value - 1, loc=stop_val.loc)
            else:
                actual_stop = ast.BinOp(op='-', left=stop_val, right=ast.Number(value=1), loc=stop_val.loc)
        elif cond.op == '>':
            if isinstance(stop_val, ast.Number):
                actual_stop = ast.Number(value=stop_val.value + 1, loc=stop_val.loc)
            else:
                actual_stop = ast.BinOp(op='+', left=stop_val, right=ast.Number(value=1), loc=stop_val.loc)

        return ast.ForNumeric(
            name=var_name,
            start=start_val,
            stop=actual_stop,
            step=step_val if not (isinstance(step_val, ast.Number) and step_val.value == 1) else None,
            body=ast.Block(stmts=new_body_stmts, loc=body.loc),
            loc=loop.loc,
        )

    def _extract_increment(self, stmt: ast.Stmt, var_name: str) -> Optional[ast.Expr]:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            if isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].name == var_name:
                val = stmt.values[0] if stmt.values else None
                if isinstance(val, ast.BinOp) and val.op == '+':
                    if isinstance(val.left, ast.Name) and val.left.name == var_name:
                        return val.right
                if isinstance(val, ast.BinOp) and val.op == '-':
                    if isinstance(val.left, ast.Name) and val.left.name == var_name:
                        if isinstance(val.right, ast.Number):
                            return ast.Number(value=-val.right.value, loc=val.right.loc)
        return None


def _const_val(e: ast.Expr):
    if isinstance(e, ast.Nil): return None
    if isinstance(e, ast.Bool): return e.value
    if isinstance(e, ast.Number): return e.value
    if isinstance(e, ast.String): return e.value
    return None

def _truthy(v) -> bool:
    return v is not None and v is not False


def restore_control_flow(tree: ast.Block) -> ast.Block:
    cfr = ControlFlowRestorer()
    tree = cfr.restore(tree)
    w2f = WhileToForConverter()
    tree = w2f.convert(tree)
    return tree
