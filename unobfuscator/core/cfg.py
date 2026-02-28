from __future__ import annotations
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from . import lua_ast as ast


@dataclass
class BasicBlock:
    id: int = 0
    stmts: List[ast.Stmt] = field(default_factory=list)
    succs: List[int] = field(default_factory=list)
    preds: List[int] = field(default_factory=list)
    condition: Optional[ast.Expr] = None
    true_branch: Optional[int] = None
    false_branch: Optional[int] = None
    is_entry: bool = False
    is_exit: bool = False


class CFG:
    def __init__(self):
        self.blocks: Dict[int, BasicBlock] = {}
        self.entry: int = 0
        self.exit: int = -1
        self._next_id = 0

    def new_block(self) -> BasicBlock:
        bb = BasicBlock(id=self._next_id)
        self.blocks[bb.id] = bb
        self._next_id += 1
        return bb

    def add_edge(self, src: int, dst: int):
        if dst not in self.blocks[src].succs:
            self.blocks[src].succs.append(dst)
        if src not in self.blocks[dst].preds:
            self.blocks[dst].preds.append(src)

    def remove_edge(self, src: int, dst: int):
        if dst in self.blocks[src].succs:
            self.blocks[src].succs.remove(dst)
        if src in self.blocks[dst].preds:
            self.blocks[dst].preds.remove(src)

    def rpo(self) -> List[int]:
        visited = set()
        order = []

        def dfs(bid):
            if bid in visited:
                return
            visited.add(bid)
            for s in self.blocks[bid].succs:
                dfs(s)
            order.append(bid)

        dfs(self.entry)
        order.reverse()
        return order

    def reverse_rpo(self) -> List[int]:
        return list(reversed(self.rpo()))


class DominatorTree:
    def __init__(self, cfg: CFG):
        self.cfg = cfg
        self.idom: Dict[int, int] = {}
        self.dom_tree: Dict[int, List[int]] = {}
        self.dom_frontier: Dict[int, Set[int]] = {}
        self._compute()

    def _compute(self):
        rpo = self.cfg.rpo()
        if not rpo:
            return
        block_to_rpo = {bid: idx for idx, bid in enumerate(rpo)}
        entry = rpo[0]

        idom = {entry: entry}
        changed = True

        def _intersect(b1, b2):
            f1, f2 = b1, b2
            while f1 != f2:
                while block_to_rpo.get(f1, len(rpo)) > block_to_rpo.get(f2, len(rpo)):
                    f1 = idom[f1]
                while block_to_rpo.get(f2, len(rpo)) > block_to_rpo.get(f1, len(rpo)):
                    f2 = idom[f2]
            return f1

        while changed:
            changed = False
            for bid in rpo[1:]:
                bb = self.cfg.blocks[bid]
                processed_preds = [p for p in bb.preds if p in idom]
                if not processed_preds:
                    continue
                new_idom = processed_preds[0]
                for p in processed_preds[1:]:
                    new_idom = _intersect(new_idom, p)
                if idom.get(bid) != new_idom:
                    idom[bid] = new_idom
                    changed = True

        self.idom = idom

        self.dom_tree = {bid: [] for bid in self.cfg.blocks}
        for bid, dom in self.idom.items():
            if bid != dom:
                self.dom_tree[dom].append(bid)

        self.dom_frontier = {bid: set() for bid in self.cfg.blocks}
        for bid in self.cfg.blocks:
            bb = self.cfg.blocks[bid]
            if len(bb.preds) >= 2:
                for p in bb.preds:
                    runner = p
                    while runner in self.idom and runner != self.idom.get(bid, bid):
                        self.dom_frontier[runner].add(bid)
                        if runner == self.idom[runner]:
                            break
                        runner = self.idom[runner]

    def dominates(self, a: int, b: int) -> bool:
        runner = b
        while runner in self.idom:
            if runner == a:
                return True
            if runner == self.idom[runner]:
                break
            runner = self.idom[runner]
        return runner == a

    def children(self, bid: int) -> List[int]:
        return self.dom_tree.get(bid, [])


class LoopInfo:
    def __init__(self, cfg: CFG, dom_tree: DominatorTree):
        self.cfg = cfg
        self.dom_tree = dom_tree
        self.loops: List[NaturalLoop] = []
        self._detect()

    def _detect(self):
        for bid in self.cfg.blocks:
            bb = self.cfg.blocks[bid]
            for s in bb.succs:
                if self.dom_tree.dominates(s, bid):
                    loop_body = self._find_loop_body(s, bid)
                    self.loops.append(NaturalLoop(header=s, back_edge=(bid, s), body=loop_body))

    def _find_loop_body(self, header: int, tail: int) -> Set[int]:
        body = {header}
        if header == tail:
            return body
        stack = [tail]
        body.add(tail)
        while stack:
            n = stack.pop()
            for p in self.cfg.blocks[n].preds:
                if p not in body:
                    body.add(p)
                    stack.append(p)
        return body

    def get_loop_for(self, bid: int) -> Optional[NaturalLoop]:
        innermost = None
        for loop in self.loops:
            if bid in loop.body:
                if innermost is None or len(loop.body) < len(innermost.body):
                    innermost = loop
        return innermost


@dataclass
class NaturalLoop:
    header: int = 0
    back_edge: Tuple[int, int] = (0, 0)
    body: Set[int] = field(default_factory=set)

    @property
    def exits(self) -> Set[int]:
        exits = set()
        for bid in self.body:
            pass
        return exits


class CFGBuilder:
    def __init__(self):
        self.cfg = CFG()
        self._break_targets: List[int] = []
        self._continue_targets: List[int] = []

    def build(self, block: ast.Block) -> CFG:
        entry = self.cfg.new_block()
        entry.is_entry = True
        self.cfg.entry = entry.id

        exit_bb = self.cfg.new_block()
        exit_bb.is_exit = True
        self.cfg.exit = exit_bb.id

        end_bb = self._build_block(block, entry)
        if end_bb is not None:
            self.cfg.add_edge(end_bb.id, exit_bb.id)

        return self.cfg

    def _build_block(self, block: ast.Block, current: BasicBlock) -> Optional[BasicBlock]:
        for stmt in block.stmts:
            if current is None:
                return None
            current = self._build_stmt(stmt, current)
        return current

    def _build_stmt(self, stmt: ast.Stmt, current: BasicBlock) -> Optional[BasicBlock]:
        if isinstance(stmt, ast.If):
            return self._build_if(stmt, current)
        elif isinstance(stmt, ast.While):
            return self._build_while(stmt, current)
        elif isinstance(stmt, ast.Repeat):
            return self._build_repeat(stmt, current)
        elif isinstance(stmt, ast.ForNumeric):
            return self._build_for_numeric(stmt, current)
        elif isinstance(stmt, ast.ForGeneric):
            return self._build_for_generic(stmt, current)
        elif isinstance(stmt, ast.Do):
            return self._build_block(stmt.body, current)
        elif isinstance(stmt, ast.Return):
            current.stmts.append(stmt)
            exit_bb = self.cfg.blocks[self.cfg.exit]
            self.cfg.add_edge(current.id, exit_bb.id)
            return None
        elif isinstance(stmt, ast.Break):
            if self._break_targets:
                self.cfg.add_edge(current.id, self._break_targets[-1])
            return None
        elif isinstance(stmt, ast.Continue):
            if self._continue_targets:
                self.cfg.add_edge(current.id, self._continue_targets[-1])
            return None
        else:
            current.stmts.append(stmt)
            return current

    def _build_if(self, stmt: ast.If, current: BasicBlock) -> Optional[BasicBlock]:
        merge = self.cfg.new_block()
        prev_bb = current

        for idx in range(len(stmt.tests)):
            cond = stmt.tests[idx]
            body = stmt.bodies[idx]

            prev_bb.condition = cond
            then_bb = self.cfg.new_block()
            prev_bb.true_branch = then_bb.id
            self.cfg.add_edge(prev_bb.id, then_bb.id)

            then_end = self._build_block(body, then_bb)
            if then_end is not None:
                self.cfg.add_edge(then_end.id, merge.id)

            if idx < len(stmt.tests) - 1:
                else_bb = self.cfg.new_block()
                prev_bb.false_branch = else_bb.id
                self.cfg.add_edge(prev_bb.id, else_bb.id)
                prev_bb = else_bb
            else:
                if stmt.else_body:
                    else_bb = self.cfg.new_block()
                    prev_bb.false_branch = else_bb.id
                    self.cfg.add_edge(prev_bb.id, else_bb.id)
                    else_end = self._build_block(stmt.else_body, else_bb)
                    if else_end is not None:
                        self.cfg.add_edge(else_end.id, merge.id)
                else:
                    prev_bb.false_branch = merge.id
                    self.cfg.add_edge(prev_bb.id, merge.id)

        if not merge.preds:
            return None
        return merge

    def _build_while(self, stmt: ast.While, current: BasicBlock) -> Optional[BasicBlock]:
        header = self.cfg.new_block()
        self.cfg.add_edge(current.id, header.id)

        body_bb = self.cfg.new_block()
        after = self.cfg.new_block()

        header.condition = stmt.condition
        header.true_branch = body_bb.id
        header.false_branch = after.id
        self.cfg.add_edge(header.id, body_bb.id)
        self.cfg.add_edge(header.id, after.id)

        self._break_targets.append(after.id)
        self._continue_targets.append(header.id)

        body_end = self._build_block(stmt.body, body_bb)
        if body_end is not None:
            self.cfg.add_edge(body_end.id, header.id)

        self._break_targets.pop()
        self._continue_targets.pop()

        return after

    def _build_repeat(self, stmt: ast.Repeat, current: BasicBlock) -> Optional[BasicBlock]:
        body_bb = self.cfg.new_block()
        self.cfg.add_edge(current.id, body_bb.id)

        after = self.cfg.new_block()

        self._break_targets.append(after.id)
        self._continue_targets.append(body_bb.id)

        body_end = self._build_block(stmt.body, body_bb)

        self._break_targets.pop()
        self._continue_targets.pop()

        if body_end is not None:
            cond_bb = self.cfg.new_block()
            self.cfg.add_edge(body_end.id, cond_bb.id)
            cond_bb.condition = stmt.condition
            cond_bb.true_branch = after.id
            cond_bb.false_branch = body_bb.id
            self.cfg.add_edge(cond_bb.id, after.id)
            self.cfg.add_edge(cond_bb.id, body_bb.id)

        return after

    def _build_for_numeric(self, stmt: ast.ForNumeric, current: BasicBlock) -> Optional[BasicBlock]:
        init_bb = self.cfg.new_block()
        current.stmts.append(ast.LocalAssign(
            names=[stmt.name], values=[stmt.start]
        ))
        self.cfg.add_edge(current.id, init_bb.id)

        header = self.cfg.new_block()
        self.cfg.add_edge(init_bb.id, header.id)

        body_bb = self.cfg.new_block()
        after = self.cfg.new_block()

        header.condition = ast.BinOp(op='<=', left=ast.Name(name=stmt.name), right=stmt.stop)
        header.true_branch = body_bb.id
        header.false_branch = after.id
        self.cfg.add_edge(header.id, body_bb.id)
        self.cfg.add_edge(header.id, after.id)

        self._break_targets.append(after.id)
        self._continue_targets.append(header.id)

        body_end = self._build_block(stmt.body, body_bb)
        if body_end is not None:
            self.cfg.add_edge(body_end.id, header.id)

        self._break_targets.pop()
        self._continue_targets.pop()

        return after

    def _build_for_generic(self, stmt: ast.ForGeneric, current: BasicBlock) -> Optional[BasicBlock]:
        header = self.cfg.new_block()
        self.cfg.add_edge(current.id, header.id)

        body_bb = self.cfg.new_block()
        after = self.cfg.new_block()

        self.cfg.add_edge(header.id, body_bb.id)
        self.cfg.add_edge(header.id, after.id)

        self._break_targets.append(after.id)
        self._continue_targets.append(header.id)

        body_end = self._build_block(stmt.body, body_bb)
        if body_end is not None:
            self.cfg.add_edge(body_end.id, header.id)

        self._break_targets.pop()
        self._continue_targets.pop()

        return after


def build_cfg(block: ast.Block) -> CFG:
    return CFGBuilder().build(block)


def compute_dominators(cfg: CFG) -> DominatorTree:
    return DominatorTree(cfg)


def find_loops(cfg: CFG, dom_tree: DominatorTree) -> LoopInfo:
    return LoopInfo(cfg, dom_tree)
