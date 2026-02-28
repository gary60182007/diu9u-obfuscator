from __future__ import annotations
from typing import Dict, Set, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from ..core import lua_ast as ast


ROBLOX_SERVICES = {
    'Players', 'Workspace', 'ReplicatedStorage', 'ServerStorage',
    'ServerScriptService', 'StarterGui', 'StarterPack', 'StarterPlayer',
    'Lighting', 'SoundService', 'Chat', 'Teams', 'TeleportService',
    'UserInputService', 'RunService', 'MarketplaceService', 'DataStoreService',
    'HttpService', 'InsertService', 'GamePassService', 'BadgeService',
    'TweenService', 'PathfindingService', 'PhysicsService', 'ContentProvider',
    'GuiService', 'PolicyService', 'LocalizationService', 'GroupService',
    'MessagingService', 'MemoryStoreService', 'TextService', 'CollectionService',
    'ContextActionService', 'HapticService', 'VRService', 'TestService',
    'LogService', 'StatsService', 'AnalyticsService',
}

ROBLOX_GLOBALS = {
    'game', 'workspace', 'script', 'Instance', 'Vector3', 'Vector2',
    'CFrame', 'Color3', 'BrickColor', 'UDim', 'UDim2', 'Enum',
    'Ray', 'Region3', 'Rect', 'TweenInfo', 'NumberRange', 'NumberSequence',
    'ColorSequence', 'PhysicalProperties', 'Font', 'OverlapParams',
    'RaycastParams', 'DockWidgetPluginGuiInfo', 'PathWaypoint',
    'wait', 'spawn', 'delay', 'tick', 'time', 'warn', 'typeof',
    'newproxy', 'getfenv', 'setfenv', 'gcinfo',
}

COMMON_METHOD_NAMES = {
    'FindFirstChild': 'child', 'WaitForChild': 'child',
    'GetService': 'service', 'GetChildren': 'children',
    'GetDescendants': 'descendants', 'Clone': 'clone',
    'Destroy': None, 'Remove': None,
    'IsA': None, 'FindFirstAncestor': 'ancestor',
    'FindFirstChildOfClass': 'child', 'FindFirstChildWhichIsA': 'child',
    'GetPropertyChangedSignal': 'signal', 'Connect': 'connection',
    'Disconnect': None, 'Fire': None, 'Wait': None,
    'Play': None, 'Stop': None, 'Pause': None, 'Resume': None,
    'TweenPosition': None, 'TweenSize': None,
    'MoveTo': None, 'SetPrimaryPartCFrame': None,
    'Kick': None, 'Ban': None,
    'SetAsync': None, 'GetAsync': 'data',
    'UpdateAsync': 'data', 'RemoveAsync': None,
    'IncrementAsync': 'value',
}

LUA_BUILTINS = {
    'print', 'error', 'warn', 'assert', 'type', 'typeof',
    'tostring', 'tonumber', 'select', 'unpack', 'pcall', 'xpcall',
    'pairs', 'ipairs', 'next', 'rawget', 'rawset', 'rawequal', 'rawlen',
    'setmetatable', 'getmetatable', 'require', 'loadstring', 'load',
    'dofile', 'collectgarbage', 'coroutine', 'string', 'table', 'math',
    'io', 'os', 'debug', 'bit32',
}


@dataclass
class VarContext:
    name: str
    assigned_from: Optional[ast.Expr] = None
    used_as_table: bool = False
    used_as_function: bool = False
    used_as_index_key: bool = False
    method_calls: List[str] = field(default_factory=list)
    field_accesses: List[str] = field(default_factory=list)
    assigned_service: Optional[str] = None
    is_loop_var: bool = False
    is_param: bool = False
    type_hint: Optional[str] = None


class ContextCollector(ast.ASTVisitor):
    def __init__(self):
        self.contexts: Dict[str, VarContext] = {}

    def collect(self, tree: ast.Block):
        self.visit(tree)

    def visit_LocalAssign(self, node: ast.LocalAssign):
        for i, name in enumerate(node.names):
            ctx = self._get_ctx(name)
            if i < len(node.values):
                ctx.assigned_from = node.values[i]
                self._analyze_assignment(ctx, node.values[i])
        for v in node.values:
            self.visit(v)

    def visit_Assign(self, node: ast.Assign):
        for i, tgt in enumerate(node.targets):
            if isinstance(tgt, ast.Name) and i < len(node.values):
                ctx = self._get_ctx(tgt.name)
                ctx.assigned_from = node.values[i]
                self._analyze_assignment(ctx, node.values[i])
        for v in node.values:
            self.visit(v)

    def visit_MethodCall(self, node: ast.MethodCall):
        if isinstance(node.object, ast.Name):
            ctx = self._get_ctx(node.object.name)
            ctx.method_calls.append(node.method)
            ctx.used_as_table = True
        self.visit(node.object)
        for a in node.args:
            self.visit(a)

    def visit_Field(self, node: ast.Field):
        if isinstance(node.table, ast.Name):
            ctx = self._get_ctx(node.table.name)
            ctx.field_accesses.append(node.name)
            ctx.used_as_table = True
        self.visit(node.table)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            ctx = self._get_ctx(node.func.name)
            ctx.used_as_function = True
        self.visit(node.func)
        for a in node.args:
            self.visit(a)

    def visit_ForNumeric(self, node: ast.ForNumeric):
        ctx = self._get_ctx(node.name)
        ctx.is_loop_var = True
        self.visit(node.start)
        self.visit(node.stop)
        if node.step:
            self.visit(node.step)
        self.visit(node.body)

    def visit_ForGeneric(self, node: ast.ForGeneric):
        for nm in node.names:
            ctx = self._get_ctx(nm)
            ctx.is_loop_var = True
        for it in node.iterators:
            self.visit(it)
        self.visit(node.body)

    def visit_FunctionDecl(self, node: ast.FunctionDecl):
        if node.func:
            for p in node.func.params:
                ctx = self._get_ctx(p)
                ctx.is_param = True
            self.visit(node.func.body)

    def _get_ctx(self, name: str) -> VarContext:
        if name not in self.contexts:
            self.contexts[name] = VarContext(name=name)
        return self.contexts[name]

    def _analyze_assignment(self, ctx: VarContext, expr: ast.Expr):
        if isinstance(expr, ast.MethodCall):
            if isinstance(expr.object, ast.Name) and expr.object.name == 'game':
                if expr.method == 'GetService' and len(expr.args) >= 1:
                    if isinstance(expr.args[0], ast.String):
                        ctx.assigned_service = expr.args[0].value
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Field):
            if isinstance(expr.func.table, ast.Name) and expr.func.table.name == 'game':
                if expr.func.name == 'GetService' and len(expr.args) >= 1:
                    if isinstance(expr.args[0], ast.String):
                        ctx.assigned_service = expr.args[0].value
        if isinstance(expr, ast.Field):
            if isinstance(expr.table, ast.Name):
                if expr.table.name in ('game', 'workspace', 'script'):
                    ctx.type_hint = expr.name
        if isinstance(expr, ast.TableConstructor):
            ctx.used_as_table = True
        if isinstance(expr, ast.FunctionExpr):
            ctx.used_as_function = True


class NameGenerator:
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.used_names: Set[str] = set()
        self.used_names.update(LUA_BUILTINS)
        self.used_names.update(ROBLOX_GLOBALS)

    def generate(self, prefix: str) -> str:
        base = self._sanitize(prefix)
        if base not in self.used_names:
            self.used_names.add(base)
            return base
        count = self.counters.get(base, 1)
        while True:
            name = f"{base}{count}"
            if name not in self.used_names:
                self.used_names.add(name)
                self.counters[base] = count + 1
                return name
            count += 1

    def _sanitize(self, name: str) -> str:
        result = ''.join(c if c.isalnum() or c == '_' else '_' for c in name)
        if result and result[0].isdigit():
            result = '_' + result
        return result or 'var'


class RenameRecovery(ast.ASTTransformer):
    def __init__(self):
        self.changes = 0
        self._rename_map: Dict[str, str] = {}
        self._name_gen = NameGenerator()
        self._contexts: Dict[str, VarContext] = {}

    def recover(self, tree: ast.Block) -> ast.Block:
        self.changes = 0
        cc = ContextCollector()
        cc.collect(tree)
        self._contexts = cc.contexts
        self._build_rename_map()
        return self.transform(tree)

    def _build_rename_map(self):
        for name, ctx in self._contexts.items():
            if not self._is_obfuscated(name):
                continue
            new_name = self._suggest_name(name, ctx)
            if new_name and new_name != name:
                self._rename_map[name] = new_name

    def _is_obfuscated(self, name: str) -> bool:
        if name in LUA_BUILTINS or name in ROBLOX_GLOBALS:
            return False
        if name.startswith('v') and name[1:].isdigit():
            return True
        if name.startswith('r') and '_' in name and name.split('_')[-1].isdigit():
            return True
        if all(c in 'lIi1' for c in name) and len(name) >= 3:
            return True
        if all(c in 'oO0' for c in name) and len(name) >= 3:
            return True
        if name.startswith('_') and len(name) >= 4 and all(c in '_lIi1oO0' for c in name):
            return True
        has_alpha = any(c.isalpha() for c in name)
        has_meaning = len(name) >= 3 and has_alpha
        if not has_meaning and len(name) <= 2:
            return True
        return False

    def _suggest_name(self, name: str, ctx: VarContext) -> Optional[str]:
        if ctx.assigned_service:
            svc = ctx.assigned_service
            short = _abbreviate_service(svc)
            return self._name_gen.generate(short)

        if ctx.assigned_from:
            suggested = self._name_from_expr(ctx.assigned_from)
            if suggested:
                return self._name_gen.generate(suggested)

        if ctx.method_calls:
            for method in ctx.method_calls:
                if method in COMMON_METHOD_NAMES and COMMON_METHOD_NAMES[method]:
                    return self._name_gen.generate(COMMON_METHOD_NAMES[method])

        if ctx.field_accesses:
            for field_name in ctx.field_accesses:
                if field_name[0].isupper() and len(field_name) >= 3:
                    return self._name_gen.generate(_camel_to_snake(field_name))

        if ctx.is_loop_var:
            return self._name_gen.generate('i')
        if ctx.is_param:
            return self._name_gen.generate('arg')
        if ctx.used_as_function:
            return self._name_gen.generate('fn')
        if ctx.used_as_table:
            return self._name_gen.generate('tbl')

        return self._name_gen.generate('var')

    def _name_from_expr(self, expr: ast.Expr) -> Optional[str]:
        if isinstance(expr, ast.MethodCall):
            if expr.method == 'GetService' and len(expr.args) >= 1:
                if isinstance(expr.args[0], ast.String):
                    return _abbreviate_service(expr.args[0].value)
            if expr.method in COMMON_METHOD_NAMES:
                hint = COMMON_METHOD_NAMES[expr.method]
                if hint:
                    return hint
            return _camel_to_snake(expr.method)

        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Name):
                if expr.func.name == 'Instance' and len(expr.args) >= 1:
                    if isinstance(expr.args[0], ast.String):
                        return _camel_to_snake(expr.args[0].value)
                if expr.func.name in ('require', 'loadstring', 'load'):
                    return 'module'
            if isinstance(expr.func, ast.Field):
                if expr.func.name == 'new':
                    if isinstance(expr.func.table, ast.Name):
                        cls = expr.func.table.name
                        return _camel_to_snake(cls)
                return _camel_to_snake(expr.func.name)

        if isinstance(expr, ast.Field):
            return _camel_to_snake(expr.name)

        if isinstance(expr, ast.Index):
            if isinstance(expr.key, ast.String):
                return _camel_to_snake(expr.key.value)

        if isinstance(expr, ast.FunctionExpr):
            return 'fn'

        if isinstance(expr, ast.TableConstructor):
            return 'tbl'

        if isinstance(expr, ast.String):
            return 'str'

        if isinstance(expr, ast.Number):
            return 'num'

        if isinstance(expr, ast.Bool):
            return 'flag'

        return None

    def transform_Name(self, node: ast.Name) -> ast.Expr:
        if node.name in self._rename_map:
            self.changes += 1
            return ast.Name(name=self._rename_map[node.name], loc=node.loc)
        return node

    def transform_LocalAssign(self, node: ast.LocalAssign) -> ast.Stmt:
        new_names = []
        for nm in node.names:
            if nm in self._rename_map:
                new_names.append(self._rename_map[nm])
                self.changes += 1
            else:
                new_names.append(nm)
        new_values = [self.transform(v) for v in node.values]
        return ast.LocalAssign(names=new_names, values=new_values, loc=node.loc)

    def transform_ForNumeric(self, node: ast.ForNumeric) -> ast.Stmt:
        name = self._rename_map.get(node.name, node.name)
        if name != node.name:
            self.changes += 1
        return ast.ForNumeric(
            name=name,
            start=self.transform(node.start),
            stop=self.transform(node.stop),
            step=self.transform(node.step) if node.step else None,
            body=self.transform(node.body),
            loc=node.loc,
        )

    def transform_ForGeneric(self, node: ast.ForGeneric) -> ast.Stmt:
        new_names = []
        for nm in node.names:
            if nm in self._rename_map:
                new_names.append(self._rename_map[nm])
                self.changes += 1
            else:
                new_names.append(nm)
        return ast.ForGeneric(
            names=new_names,
            iterators=[self.transform(it) for it in node.iterators],
            body=self.transform(node.body),
            loc=node.loc,
        )

    def transform_FunctionDecl(self, node: ast.FunctionDecl) -> ast.Stmt:
        new_name = node.name
        if isinstance(node.name, ast.Name) and node.name.name in self._rename_map:
            new_name = ast.Name(name=self._rename_map[node.name.name], loc=node.name.loc)
            self.changes += 1
        new_params = []
        if node.func:
            for p in node.func.params:
                if p in self._rename_map:
                    new_params.append(self._rename_map[p])
                    self.changes += 1
                else:
                    new_params.append(p)
            new_func = ast.FunctionExpr(
                params=new_params,
                has_vararg=node.func.has_vararg,
                body=self.transform(node.func.body),
                loc=node.func.loc,
            )
        else:
            new_func = node.func
        return ast.FunctionDecl(
            name=new_name if isinstance(new_name, ast.Expr) else node.name,
            is_local=node.is_local,
            func=new_func,
            loc=node.loc,
        )

    def transform_Assign(self, node: ast.Assign) -> ast.Stmt:
        new_targets = [self.transform(t) for t in node.targets]
        new_values = [self.transform(v) for v in node.values]
        return ast.Assign(targets=new_targets, values=new_values, loc=node.loc)


def _abbreviate_service(service_name: str) -> str:
    abbrevs = {
        'Players': 'players',
        'Workspace': 'workspace',
        'ReplicatedStorage': 'repStorage',
        'ServerStorage': 'serverStorage',
        'ServerScriptService': 'sss',
        'StarterGui': 'starterGui',
        'StarterPack': 'starterPack',
        'StarterPlayer': 'starterPlayer',
        'Lighting': 'lighting',
        'SoundService': 'soundService',
        'UserInputService': 'uis',
        'RunService': 'runService',
        'MarketplaceService': 'mps',
        'DataStoreService': 'dss',
        'HttpService': 'http',
        'TweenService': 'tweenService',
        'PathfindingService': 'pathService',
        'ContentProvider': 'contentProvider',
        'TeleportService': 'teleportService',
        'CollectionService': 'collectionService',
        'ContextActionService': 'cas',
        'TextService': 'textService',
        'MessagingService': 'msgService',
        'MemoryStoreService': 'memStore',
        'GuiService': 'guiService',
        'Chat': 'chat',
        'Teams': 'teams',
    }
    return abbrevs.get(service_name, _camel_to_snake(service_name))


def _camel_to_snake(name: str) -> str:
    if not name:
        return 'var'
    if len(name) <= 2:
        return name.lower()
    result = [name[0].lower()]
    for i in range(1, len(name)):
        c = name[i]
        if c.isupper() and i + 1 < len(name) and name[i + 1].islower():
            result.append('_')
            result.append(c.lower())
        elif c.isupper():
            result.append(c.lower())
        else:
            result.append(c)
    s = ''.join(result)
    while '__' in s:
        s = s.replace('__', '_')
    return s.strip('_') or 'var'


def recover_names(tree: ast.Block) -> ast.Block:
    rr = RenameRecovery()
    return rr.recover(tree)
