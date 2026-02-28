from __future__ import annotations
from typing import Dict, Set, List, Optional, Tuple
from dataclasses import dataclass, field
from .cfg import CFG, DominatorTree, BasicBlock
from . import lua_ast as ast


@dataclass
class PhiFunction:
    var: str
    dest: str = ""
    sources: Dict[int, str] = field(default_factory=dict)
    block_id: int = 0


@dataclass
class SSADef:
    var: str
    version: int
    block_id: int
    stmt: Optional[ast.Stmt] = None
    phi: Optional[PhiFunction] = None


class SSAForm:
    def __init__(self, cfg: CFG, dom_tree: DominatorTree):
        self.cfg = cfg
        self.dom_tree = dom_tree
        self.phis: Dict[int, List[PhiFunction]] = {bid: [] for bid in cfg.blocks}
        self.var_versions: Dict[str, int] = {}
        self.var_stacks: Dict[str, List[str]] = {}
        self.defs: Dict[str, SSADef] = {}
        self.uses: Dict[str, Set[str]] = {}
        self._all_vars: Set[str] = set()
        self._def_sites: Dict[str, Set[int]] = {}

    def build(self):
        self._collect_vars()
        self._insert_phis()
        self._rename()

    def _collect_vars(self):
        for bid, bb in self.cfg.blocks.items():
            for stmt in bb.stmts:
                defs, uses = self._stmt_defs_uses(stmt)
                for v in defs:
                    self._all_vars.add(v)
                    if v not in self._def_sites:
                        self._def_sites[v] = set()
                    self._def_sites[v].add(bid)
                for v in uses:
                    self._all_vars.add(v)

    def _insert_phis(self):
        for var in self._all_vars:
            if var not in self._def_sites:
                continue
            worklist = list(self._def_sites[var])
            placed = set()
            while worklist:
                bid = worklist.pop()
                for df_bid in self.dom_tree.dom_frontier.get(bid, set()):
                    if df_bid not in placed:
                        placed.add(df_bid)
                        phi = PhiFunction(var=var, block_id=df_bid)
                        self.phis[df_bid].append(phi)
                        if df_bid not in self._def_sites.get(var, set()):
                            worklist.append(df_bid)

    def _rename(self):
        for v in self._all_vars:
            self.var_versions[v] = 0
            self.var_stacks[v] = []

        self._rename_block(self.cfg.entry)

    def _new_name(self, var: str) -> str:
        self.var_versions[var] = self.var_versions.get(var, 0) + 1
        ver = self.var_versions[var]
        name = f"{var}_{ver}"
        if var not in self.var_stacks:
            self.var_stacks[var] = []
        self.var_stacks[var].append(name)
        return name

    def _current_name(self, var: str) -> str:
        stack = self.var_stacks.get(var, [])
        if stack:
            return stack[-1]
        return f"{var}_0"

    def _rename_block(self, bid: int):
        bb = self.cfg.blocks.get(bid)
        if bb is None:
            return

        old_stack_sizes = {v: len(self.var_stacks.get(v, [])) for v in self._all_vars}

        for phi in self.phis[bid]:
            phi.dest = self._new_name(phi.var)

        new_stmts = []
        for stmt in bb.stmts:
            uses_vars = self._stmt_uses(stmt)
            for var_name in uses_vars:
                pass

            defs_vars = self._stmt_defs(stmt)
            for var_name in defs_vars:
                self._new_name(var_name)

            new_stmts.append(stmt)
        bb.stmts = new_stmts

        for succ_id in bb.succs:
            for phi in self.phis.get(succ_id, []):
                phi.sources[bid] = self._current_name(phi.var)

        for child in self.dom_tree.children(bid):
            self._rename_block(child)

        for v in self._all_vars:
            target_size = old_stack_sizes.get(v, 0)
            while len(self.var_stacks.get(v, [])) > target_size:
                self.var_stacks[v].pop()

    def _stmt_defs_uses(self, stmt: ast.Stmt) -> Tuple[Set[str], Set[str]]:
        return self._stmt_defs(stmt), self._stmt_uses(stmt)

    def _stmt_defs(self, stmt: ast.Stmt) -> Set[str]:
        defs = set()
        if isinstance(stmt, ast.LocalAssign):
            for name in stmt.names:
                defs.add(name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    defs.add(target.name)
        elif isinstance(stmt, ast.FunctionDecl):
            if stmt.is_local and isinstance(stmt.name, ast.Name):
                defs.add(stmt.name.name)
        elif isinstance(stmt, ast.ForNumeric):
            defs.add(stmt.name)
        elif isinstance(stmt, ast.ForGeneric):
            for name in stmt.names:
                defs.add(name)
        return defs

    def _stmt_uses(self, stmt: ast.Stmt) -> Set[str]:
        uses = set()
        self._collect_expr_uses(stmt, uses)
        return uses

    def _collect_expr_uses(self, node: ast.Node, uses: Set[str]):
        if isinstance(node, ast.Name):
            uses.add(node.name)
        for child in node.children():
            self._collect_expr_uses(child, uses)

    def get_reaching_def(self, var: str) -> Optional[str]:
        return self._current_name(var)

    def get_phi_functions(self, block_id: int) -> List[PhiFunction]:
        return self.phis.get(block_id, [])

    def all_phis(self) -> List[PhiFunction]:
        result = []
        for bid in self.phis:
            result.extend(self.phis[bid])
        return result


def build_ssa(cfg: CFG, dom_tree: DominatorTree) -> SSAForm:
    ssa = SSAForm(cfg, dom_tree)
    ssa.build()
    return ssa
