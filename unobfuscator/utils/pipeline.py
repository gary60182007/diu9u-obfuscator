from __future__ import annotations
from typing import List, Optional, Dict, Callable, Any, Tuple
from dataclasses import dataclass, field
import time
import traceback
from ..core import lua_ast as ast
from ..core.lua_parser import parse as lua_parse
from ..core.lua_emitter import emit
from ..core.sandbox import LuaSandbox


@dataclass
class PassResult:
    name: str
    success: bool = True
    changes: int = 0
    duration: float = 0.0
    error: Optional[str] = None
    tree: Optional[ast.Block] = None


@dataclass
class PipelineStats:
    total_passes: int = 0
    total_changes: int = 0
    total_duration: float = 0.0
    pass_results: List[PassResult] = field(default_factory=list)
    detected_obfuscator: Optional[str] = None
    original_size: int = 0
    final_size: int = 0

    def summary(self) -> str:
        lines = [
            f"Pipeline Summary:",
            f"  Passes run: {self.total_passes}",
            f"  Total changes: {self.total_changes}",
            f"  Duration: {self.total_duration:.2f}s",
            f"  Detected obfuscator: {self.detected_obfuscator or 'unknown'}",
            f"  Size reduction: {self.original_size} -> {self.final_size} chars",
        ]
        for pr in self.pass_results:
            status = "OK" if pr.success else "FAIL"
            lines.append(f"  [{status}] {pr.name}: {pr.changes} changes, {pr.duration:.3f}s")
            if pr.error:
                lines.append(f"         Error: {pr.error}")
        return '\n'.join(lines)


@dataclass
class PassConfig:
    name: str
    func: Callable
    enabled: bool = True
    max_iterations: int = 1
    requires: List[str] = field(default_factory=list)
    args: Dict[str, Any] = field(default_factory=dict)


class Pipeline:
    def __init__(self, sandbox: Optional[LuaSandbox] = None):
        self.sandbox = sandbox or LuaSandbox(op_limit=20_000_000, timeout=60.0)
        self.passes: List[PassConfig] = []
        self.stats = PipelineStats()
        self._on_progress: Optional[Callable[[str, int, int], None]] = None

    def add_pass(self, name: str, func: Callable, max_iterations: int = 1,
                 requires: Optional[List[str]] = None, **kwargs):
        self.passes.append(PassConfig(
            name=name, func=func, max_iterations=max_iterations,
            requires=requires or [], args=kwargs,
        ))

    def set_progress_callback(self, callback: Callable[[str, int, int], None]):
        self._on_progress = callback

    def run(self, source: str) -> Tuple[str, PipelineStats]:
        self.stats = PipelineStats()
        self.stats.original_size = len(source)
        self.original_source = source

        tree = lua_parse(source)

        self.stats.detected_obfuscator = self._detect_obfuscator(tree)

        total = len(self.passes)
        for i, pc in enumerate(self.passes):
            if not pc.enabled:
                continue
            if self._on_progress:
                self._on_progress(pc.name, i + 1, total)

            result = self._run_pass(pc, tree)
            self.stats.pass_results.append(result)
            self.stats.total_passes += 1
            self.stats.total_changes += result.changes
            self.stats.total_duration += result.duration

            if result.success and result.tree is not None:
                tree = result.tree

        output = emit(tree)
        self.stats.final_size = len(output)
        return output, self.stats

    def _run_pass(self, pc: PassConfig, tree: ast.Block) -> PassResult:
        start = time.time()
        try:
            result_tree = tree
            total_changes = 0
            for _ in range(pc.max_iterations):
                ret = pc.func(result_tree, **pc.args)
                if isinstance(ret, tuple):
                    result_tree, changes = ret[0], ret[1] if len(ret) > 1 else 0
                elif isinstance(ret, ast.Block):
                    result_tree = ret
                    changes = 0
                else:
                    break
                if isinstance(changes, int):
                    total_changes += changes
                    if changes == 0:
                        break
                else:
                    break
            elapsed = time.time() - start
            return PassResult(
                name=pc.name, success=True, changes=total_changes,
                duration=elapsed, tree=result_tree,
            )
        except Exception as e:
            elapsed = time.time() - start
            return PassResult(
                name=pc.name, success=False, changes=0,
                duration=elapsed, error=f"{type(e).__name__}: {e}",
            )

    def _detect_obfuscator(self, tree: ast.Block) -> Optional[str]:
        from ..targets.vm_lift import VMPatternMatcher
        pm = VMPatternMatcher()
        detected = pm.detect_vm_type(tree)
        if detected:
            return detected

        source = emit(tree)
        from ..targets.ironbrew3 import IronBrew3Deobfuscator
        if IronBrew3Deobfuscator.detect(source):
            return 'ironbrew3'

        markers = {
            'ironbrew': ['IronBrew', 'IBRW', 'IB2'],
            'psu': ['PSU', 'Prometheus'],
            'moonsec': ['MoonSec', 'moonsec', 'MSEC'],
            'luraph': ['Luraph', 'luraph', 'LRPH'],
        }
        for name, keywords in markers.items():
            for kw in keywords:
                if kw in source:
                    return name

        has_loadstring = 'loadstring' in source or 'load(' in source
        has_long_string = any(isinstance(n, ast.String) and len(n.value) > 500
                             for n in _walk(tree))
        if has_loadstring and has_long_string:
            return 'loadstring_wrapper'

        return None


def create_default_pipeline(sandbox: Optional[LuaSandbox] = None) -> Pipeline:
    p = Pipeline(sandbox)

    from ..passes.loadstring_unwrap import MultiLayerUnwrapper
    from ..passes.state_machine_deobf import deobfuscate_state_machine
    from ..passes.string_decrypt import StringDecryptor
    from ..passes.normalize import Normalizer, VariableInliner
    from ..passes.mba_simplify import MBASimplifier
    from ..passes.expr_simplify import simplify_exprs
    from ..passes.dead_code import eliminate_dead_code
    from ..passes.junk_removal import remove_junk
    from ..passes.copy_propagation import propagate_copies
    from ..passes.control_flow import restore_control_flow
    from ..passes.rename_recovery import recover_names

    sb = sandbox or p.sandbox

    def run_unwrap(tree: ast.Block, **kw):
        uw = MultiLayerUnwrapper(sb)
        source = emit(tree)
        result_src = uw.unwrap(source)
        if result_src != source:
            return lua_parse(result_src), 1
        return tree, 0

    def run_string_decrypt(tree: ast.Block, **kw):
        sd = StringDecryptor(sb)
        return sd.decrypt(tree)

    def run_normalize(tree: ast.Block, **kw):
        n = Normalizer()
        result = n.normalize(tree)
        return result, n.changes

    def run_inline(tree: ast.Block, **kw):
        vi = VariableInliner()
        result = vi.inline(tree)
        return result, vi.changes

    def run_mba(tree: ast.Block, **kw):
        m = MBASimplifier()
        result = m.simplify(tree)
        return result, m.changes

    def run_expr(tree: ast.Block, **kw):
        return simplify_exprs(tree)

    def run_dce(tree: ast.Block, **kw):
        return eliminate_dead_code(tree)

    def run_junk(tree: ast.Block, **kw):
        return remove_junk(tree)

    def run_copy(tree: ast.Block, **kw):
        return propagate_copies(tree)

    def run_cf(tree: ast.Block, **kw):
        return restore_control_flow(tree)

    def run_rename(tree: ast.Block, **kw):
        return recover_names(tree)

    def run_state_machine(tree: ast.Block, **kw):
        return deobfuscate_state_machine(
            tree,
            original_source=p.original_source if hasattr(p, 'original_source') else None,
            sandbox=LuaSandbox(op_limit=50_000_000, timeout=60.0),
        )

    p.add_pass('loadstring_unwrap', run_unwrap)
    p.add_pass('state_machine_deobf', run_state_machine)
    p.add_pass('string_decrypt', run_string_decrypt)
    p.add_pass('normalize', run_normalize, max_iterations=5)
    p.add_pass('mba_simplify', run_mba, max_iterations=5)
    p.add_pass('expr_simplify', run_expr)
    p.add_pass('dead_code_elimination', run_dce)
    p.add_pass('junk_removal', run_junk)
    p.add_pass('copy_propagation', run_copy)
    p.add_pass('variable_inline', run_inline, max_iterations=3)
    p.add_pass('control_flow_restore', run_cf)
    p.add_pass('normalize_final', run_normalize, max_iterations=3)
    p.add_pass('expr_simplify_final', run_expr)
    p.add_pass('dead_code_final', run_dce)
    p.add_pass('rename_recovery', run_rename)

    return p


def create_vm_pipeline(obfuscator_type: str, sandbox: Optional[LuaSandbox] = None, **kwargs) -> Pipeline:
    p = create_default_pipeline(sandbox)

    sb = sandbox or p.sandbox

    if obfuscator_type == 'ironbrew':
        from ..targets.ironbrew2 import IronBrew2Deobfuscator

        def run_ib2(tree: ast.Block, **kw):
            d = IronBrew2Deobfuscator(sb)
            source = emit(tree)
            result = d.deobfuscate(source)
            return result if result else tree

        p.passes.insert(0, PassConfig(name='ironbrew2_lift', func=run_ib2))

    elif obfuscator_type == 'psu':
        from ..targets.psu import PSUDeobfuscator

        def run_psu(tree: ast.Block, **kw):
            d = PSUDeobfuscator(sb)
            source = emit(tree)
            result = d.deobfuscate(source)
            return result if result else tree

        p.passes.insert(0, PassConfig(name='psu_lift', func=run_psu))

    elif obfuscator_type == 'moonsec':
        from ..targets.moonsec import MoonsecV3Deobfuscator

        def run_moonsec(tree: ast.Block, **kw):
            d = MoonsecV3Deobfuscator(sb)
            source = emit(tree)
            result = d.deobfuscate(source)
            return result if result else tree

        p.passes.insert(0, PassConfig(name='moonsec_lift', func=run_moonsec))

    elif obfuscator_type == 'luraph':
        from ..targets.luraph import LuraphDeobfuscator

        inspect_path = kwargs.get('inspect_path')

        def run_luraph(tree: ast.Block, **kw):
            d = LuraphDeobfuscator(sb, inspect_path=inspect_path)
            source = emit(tree)
            result = d.deobfuscate(source)
            return result if result else tree

        p.passes.insert(0, PassConfig(name='luraph_lift', func=run_luraph))

    elif obfuscator_type == 'ironbrew3':
        from ..targets.ironbrew3 import IronBrew3Deobfuscator

        def run_ib3(tree: ast.Block, **kw):
            d = IronBrew3Deobfuscator()
            source = emit(tree)
            result = d.deobfuscate(source)
            return result if result else tree

        p.passes.insert(0, PassConfig(name='ironbrew3_lift', func=run_ib3))

    elif obfuscator_type == 'generic_vm':
        from ..targets.vm_lift import VMLifter

        def run_vm_lift(tree: ast.Block, **kw):
            lifter = VMLifter(sb)
            source = emit(tree)
            result = lifter.lift(source)
            return result if result else tree

        p.passes.insert(0, PassConfig(name='vm_lift', func=run_vm_lift))

    return p


def _walk(node):
    if node is None:
        return
    yield node
    if isinstance(node, ast.Node):
        for child in node.children():
            yield from _walk(child)
