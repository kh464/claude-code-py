from __future__ import annotations

import ast
import copy
import re
from pathlib import Path
from typing import Any


_SUPPORTED_KINDS: set[str] = {"extract", "move", "inline"}


def _normalize_refactor_kind(kind: str | None) -> str:
    text = str(kind or "").strip().lower()
    if "extract" in text:
        return "extract"
    if "move" in text:
        return "move"
    if "inline" in text:
        return "inline"
    return "other"


def _leading_spaces(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _failure(*, kind: str | None, reason: str, apply: bool) -> dict[str, Any]:
    return {
        "backend": "semantic_fallback",
        "applied": False,
        "selected": None,
        "files_changed": 0,
        "occurrences": 0,
        "changes": [],
        "fallback_attempted": True,
        "fallback_kind": str(kind or ""),
        "fallback_error": reason,
        "fallback_apply_requested": bool(apply),
    }


class SemanticRefactorFallback:
    def __init__(self, *, root: Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def supported_kinds() -> tuple[str, ...]:
        return tuple(sorted(_SUPPORTED_KINDS))

    def apply(
        self,
        *,
        path: str | Path,
        target_path: str | Path | None = None,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        normalized_kind: str | None,
        apply: bool,
        reason: str,
    ) -> dict[str, Any]:
        kind = _normalize_refactor_kind(normalized_kind)
        if kind not in _SUPPORTED_KINDS:
            return _failure(kind=normalized_kind, reason="fallback_kind_unresolved", apply=apply)

        target = Path(path).expanduser().resolve()
        if not target.exists() or not target.is_file():
            return _failure(kind=kind, reason="target_not_found", apply=apply)
        if target.suffix != ".py":
            return _failure(kind=kind, reason="python_only_fallback", apply=apply)

        if kind == "extract":
            return self._apply_extract(
                target=target,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                apply=bool(apply),
                reason=reason,
            )
        if kind == "move":
            return self._apply_move(
                target=target,
                move_target=Path(target_path).expanduser().resolve() if target_path is not None else None,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                apply=bool(apply),
                reason=reason,
            )
        if kind == "inline":
            return self._apply_inline(
                target=target,
                start_line=int(start_line),
                start_character=int(start_character),
                end_line=int(end_line),
                end_character=int(end_character),
                apply=bool(apply),
                reason=reason,
            )
        return _failure(kind=kind, reason="fallback_kind_unresolved", apply=apply)

    @staticmethod
    def _resolve_line_span(
        *,
        lines: list[str],
        start_line: int,
        end_line: int,
        end_character: int,
    ) -> tuple[int, int] | None:
        if not lines:
            return None
        start = max(0, min(int(start_line), len(lines) - 1))
        end = max(0, min(int(end_line), len(lines) - 1))
        if int(end_character) <= 0 and end > start:
            end -= 1
        if end < start:
            return None
        return start, end

    @staticmethod
    def _find_containing_function(
        *,
        source: str,
        start_line_1based: int,
        end_line_1based: int,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        candidates: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            node_start = int(getattr(node, "lineno", 0))
            node_end = int(getattr(node, "end_lineno", node_start))
            if node_start <= start_line_1based <= node_end and node_start <= end_line_1based <= node_end:
                candidates.append(node)
        if not candidates:
            return None
        candidates.sort(key=lambda item: (int(getattr(item, "end_lineno", item.lineno)) - int(item.lineno), int(item.lineno)))
        return candidates[0]

    @staticmethod
    def _line_starts(text: str) -> list[int]:
        starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                starts.append(index + 1)
        return starts

    @classmethod
    def _position_to_offset(cls, text: str, *, line_1based: int, character: int) -> int:
        starts = cls._line_starts(text)
        if not starts:
            return 0
        safe_line_index = max(0, min(int(line_1based) - 1, len(starts) - 1))
        line_start = starts[safe_line_index]
        if safe_line_index + 1 < len(starts):
            line_end = starts[safe_line_index + 1] - 1
        else:
            line_end = len(text)
        return max(line_start, min(line_start + max(0, int(character)), line_end))

    @staticmethod
    def _normalize_newline(text: str) -> str:
        if not text:
            return ""
        return text if text.endswith("\n") else f"{text}\n"

    @staticmethod
    def _append_python_block(*, existing: str, block: str) -> str:
        block_text = block.strip("\n")
        if not block_text:
            return SemanticRefactorFallback._normalize_newline(existing)
        existing_text = existing.rstrip("\n")
        if not existing_text:
            return f"{block_text}\n"
        return f"{existing_text}\n\n{block_text}\n"

    @staticmethod
    def _build_text_from_lines(*, lines: list[str], trailing_newline: bool) -> str:
        if not lines:
            return ""
        text = "\n".join(lines)
        if trailing_newline:
            text += "\n"
        return text

    @staticmethod
    def _find_module_docstring_end_line(source: str) -> int:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return 0
        if not tree.body:
            return 0
        first = tree.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            return int(getattr(first, "end_lineno", first.lineno))
        return 0

    @classmethod
    def _ensure_import_line(cls, *, source: str, module_name: str, symbol_name: str) -> str:
        import_line = f"from {module_name} import {symbol_name}"
        existing_lines = source.splitlines()
        if any(line.strip() == import_line for line in existing_lines):
            return source
        trailing_newline = source.endswith("\n")
        lines = list(existing_lines)
        insert_at = cls._find_module_docstring_end_line(source)
        while insert_at < len(lines) and (
            lines[insert_at].startswith("import ")
            or lines[insert_at].startswith("from ")
            or not lines[insert_at].strip()
        ):
            insert_at += 1
        lines.insert(insert_at, import_line)
        return cls._build_text_from_lines(lines=lines, trailing_newline=trailing_newline or bool(lines))

    def _module_name_for_path(self, path: Path) -> str | None:
        try:
            relative = path.resolve().relative_to(self.root)
        except ValueError:
            return None
        if relative.suffix != ".py":
            return None
        parts = list(relative.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            return None
        return ".".join(parts)

    def _module_path_for_name(self, module_name: str) -> Path | None:
        raw = str(module_name or "").strip()
        if not raw:
            return None
        parts = [part for part in raw.split(".") if part]
        if not parts:
            return None
        module_file = (self.root / Path(*parts)).with_suffix(".py")
        if module_file.exists() and module_file.is_file():
            return module_file.expanduser().resolve()
        package_init = self.root / Path(*parts) / "__init__.py"
        if package_init.exists() and package_init.is_file():
            return package_init.expanduser().resolve()
        return None

    @staticmethod
    def _node_span_lines(node: ast.AST) -> tuple[int, int]:
        node_start = int(getattr(node, "lineno", 0))
        node_end = int(getattr(node, "end_lineno", node_start))
        decorators = getattr(node, "decorator_list", [])
        if isinstance(decorators, list) and decorators:
            decorator_starts = [int(getattr(item, "lineno", node_start)) for item in decorators]
            positive = [line for line in decorator_starts if line > 0]
            if positive:
                node_start = min([node_start, *positive]) if node_start > 0 else min(positive)
        return node_start, node_end

    @staticmethod
    def _decorator_is_staticmethod(decorator: ast.AST) -> bool:
        if isinstance(decorator, ast.Name):
            return decorator.id == "staticmethod"
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "staticmethod"
        return False

    @staticmethod
    def _decorator_is_classmethod(decorator: ast.AST) -> bool:
        if isinstance(decorator, ast.Name):
            return decorator.id == "classmethod"
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "classmethod"
        return False

    @staticmethod
    def _function_uses_name(node: ast.FunctionDef | ast.AsyncFunctionDef, symbol: str) -> bool:
        for item in ast.walk(node):
            if isinstance(item, ast.Name) and item.id == symbol and isinstance(item.ctx, ast.Load):
                return True
        return False

    @staticmethod
    def _extract_name_targets(target: ast.AST) -> list[str]:
        if isinstance(target, ast.Name):
            return [target.id]
        if isinstance(target, (ast.Tuple, ast.List)):
            names: list[str] = []
            for item in target.elts:
                names.extend(SemanticRefactorFallback._extract_name_targets(item))
            return names
        return []

    @staticmethod
    def _collect_simple_constructor_factories(
        *,
        tree: ast.Module,
        class_name: str,
        seed_factory_names: set[str] | None = None,
        seed_module_factory_attrs: dict[str, set[str]] | None = None,
    ) -> set[str]:
        def _is_safe_factory_call(
            value: ast.Call,
            *,
            known_factory_names: set[str],
        ) -> bool:
            if isinstance(value.func, ast.Name):
                return value.func.id in known_factory_names
            if (
                isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name)
                and seed_module_factory_attrs
            ):
                module_alias = value.func.value.id
                allowed_attrs = seed_module_factory_attrs.get(module_alias, set())
                return value.func.attr in allowed_attrs
            return False

        def _is_safe_value(
            value: ast.AST | None,
            *,
            known_factory_names: set[str],
            safe_locals: set[str],
        ) -> bool:
            if value is None:
                return False
            if isinstance(value, ast.Name):
                return value.id in safe_locals
            if isinstance(value, ast.Call):
                return _is_safe_factory_call(value, known_factory_names=known_factory_names)
            if isinstance(value, ast.IfExp):
                return _is_safe_value(
                    value.body,
                    known_factory_names=known_factory_names,
                    safe_locals=safe_locals,
                ) and _is_safe_value(
                    value.orelse,
                    known_factory_names=known_factory_names,
                    safe_locals=safe_locals,
                )
            return False

        def _analyze_block(
            stmts: list[ast.stmt],
            *,
            known_factory_names: set[str],
            incoming_safe_locals: set[str],
        ) -> tuple[bool, bool, set[str]]:
            safe_locals = set(incoming_safe_locals)
            for index, stmt in enumerate(stmts):
                if (
                    index == 0
                    and isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    continue
                if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                    value: ast.AST | None = stmt.value
                    raw_targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                    targets: list[str] = []
                    for raw_target in raw_targets:
                        targets.extend(SemanticRefactorFallback._extract_name_targets(raw_target))
                    if not targets:
                        return False, False, safe_locals
                    is_safe = _is_safe_value(
                        value,
                        known_factory_names=known_factory_names,
                        safe_locals=safe_locals,
                    )
                    for name in targets:
                        if is_safe:
                            safe_locals.add(name)
                        elif name in safe_locals:
                            safe_locals.remove(name)
                    continue
                if isinstance(stmt, ast.If):
                    ok_body, ret_body, out_body = _analyze_block(
                        stmt.body,
                        known_factory_names=known_factory_names,
                        incoming_safe_locals=set(safe_locals),
                    )
                    ok_else, ret_else, out_else = _analyze_block(
                        stmt.orelse,
                        known_factory_names=known_factory_names,
                        incoming_safe_locals=set(safe_locals),
                    )
                    if not ok_body or not ok_else:
                        return False, False, safe_locals
                    if ret_body and ret_else:
                        return True, True, safe_locals
                    if ret_body and not ret_else:
                        safe_locals = out_else
                        continue
                    if ret_else and not ret_body:
                        safe_locals = out_body
                        continue
                    safe_locals = out_body.intersection(out_else)
                    continue
                if isinstance(stmt, ast.Return):
                    if not _is_safe_value(
                        stmt.value,
                        known_factory_names=known_factory_names,
                        safe_locals=safe_locals,
                    ):
                        return False, False, safe_locals
                    return True, True, safe_locals
                if isinstance(stmt, ast.Pass):
                    continue
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    continue
                return False, False, safe_locals
            return True, False, safe_locals

        factory_names: set[str] = set()
        seed_names = {class_name}
        if seed_factory_names:
            seed_names.update(str(name) for name in seed_factory_names if str(name).strip())
        changed = True
        while changed:
            changed = False
            known_factory_names = set(seed_names).union(factory_names)
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name in factory_names:
                    continue
                ok, returns_safe, _safe_locals = _analyze_block(
                    list(node.body),
                    known_factory_names=known_factory_names,
                    incoming_safe_locals=set(),
                )
                if not ok or not returns_safe:
                    continue
                factory_names.add(node.name)
                changed = True
        return factory_names

    @staticmethod
    def _imported_symbols_from_module(*, source: str, module_name: str) -> set[str]:
        symbols: set[str] = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return symbols
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if int(node.level) != 0:
                continue
            if str(node.module or "") != module_name:
                continue
            for alias in node.names:
                raw = str(alias.name or "")
                if not raw or raw == "*":
                    continue
                local_name = str(alias.asname or raw).strip()
                if local_name:
                    symbols.add(local_name)
        return symbols

    @staticmethod
    def _imported_symbol_alias_map_from_module(*, source: str, module_name: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return aliases
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if int(node.level) != 0:
                continue
            if str(node.module or "") != module_name:
                continue
            for alias in node.names:
                raw_name = str(alias.name or "").strip()
                if not raw_name or raw_name == "*":
                    continue
                local_name = str(alias.asname or raw_name).strip()
                if local_name:
                    aliases[local_name] = raw_name
        return aliases

    @staticmethod
    def _imported_module_aliases_from_module(*, source: str, module_name: str) -> set[str]:
        aliases: set[str] = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return aliases
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import):
                continue
            for alias in node.names:
                raw_module = str(alias.name or "").strip()
                if raw_module != module_name:
                    continue
                local_name = str(alias.asname or raw_module.split(".")[0]).strip()
                if local_name:
                    aliases.add(local_name)
        return aliases

    @staticmethod
    def _collect_parameter_passthrough_wrappers(
        tree: ast.Module,
        *,
        seed_wrappers: dict[str, set[tuple[int, str]]] | None = None,
        seed_module_wrappers: dict[str, dict[str, set[tuple[int, str]]]] | None = None,
    ) -> dict[str, set[tuple[int, str]]]:
        wrappers: dict[str, set[tuple[int, str]]] = {
            str(name): set(entries)
            for name, entries in dict(seed_wrappers or {}).items()
            if str(name).strip()
        }
        module_wrappers = {
            str(alias): {
                str(name): set(entries)
                for name, entries in dict(wrapper_map).items()
                if str(name).strip()
            }
            for alias, wrapper_map in dict(seed_module_wrappers or {}).items()
            if str(alias).strip()
        }
        function_meta: dict[str, tuple[list[str], ast.AST | None]] = {}

        def _resolve_alias_expression(
            value: ast.AST | None,
            *,
            alias_map: dict[str, ast.AST],
            max_hops: int = 8,
        ) -> ast.AST | None:
            current = value
            hops = 0
            while isinstance(current, ast.Name) and current.id in alias_map and hops < max_hops:
                current = alias_map[current.id]
                hops += 1
            if isinstance(current, ast.IfExp):
                body = _resolve_alias_expression(current.body, alias_map=alias_map, max_hops=max_hops)
                orelse = _resolve_alias_expression(current.orelse, alias_map=alias_map, max_hops=max_hops)
                return ast.IfExp(
                    test=copy.deepcopy(current.test),
                    body=body if body is not None else current.body,
                    orelse=orelse if orelse is not None else current.orelse,
                )
            if isinstance(current, ast.Call):
                args = []
                for arg in current.args:
                    resolved = _resolve_alias_expression(arg, alias_map=alias_map, max_hops=max_hops)
                    args.append(resolved if resolved is not None else arg)
                keywords: list[ast.keyword] = []
                for keyword in current.keywords:
                    resolved = _resolve_alias_expression(keyword.value, alias_map=alias_map, max_hops=max_hops)
                    keywords.append(ast.keyword(arg=keyword.arg, value=resolved if resolved is not None else keyword.value))
                return ast.Call(func=copy.deepcopy(current.func), args=args, keywords=keywords)
            return current

        def _bind_assignment_aliases(
            stmt: ast.stmt,
            *,
            alias_map: dict[str, ast.AST],
        ) -> dict[str, ast.AST] | None:
            current_map = dict(alias_map)
            if isinstance(stmt, ast.Assign):
                value = _resolve_alias_expression(stmt.value, alias_map=current_map)
                if value is None:
                    return None
                targets: list[str] = []
                for raw_target in stmt.targets:
                    targets.extend(SemanticRefactorFallback._extract_name_targets(raw_target))
                if not targets:
                    return None
                for target in targets:
                    current_map[target] = value
                return current_map
            if isinstance(stmt, ast.AnnAssign):
                value = _resolve_alias_expression(stmt.value, alias_map=current_map)
                if value is None:
                    return None
                targets = SemanticRefactorFallback._extract_name_targets(stmt.target)
                if not targets:
                    return None
                for target in targets:
                    current_map[target] = value
                return current_map
            return None

        def _resolve_return_expression(
            stmts: list[ast.stmt],
            *,
            alias_map: dict[str, ast.AST],
            depth: int = 0,
        ) -> ast.AST | None:
            if depth > 8:
                return None
            current_map = dict(alias_map)
            index = 0
            while index < len(stmts):
                stmt = stmts[index]
                bound_aliases = _bind_assignment_aliases(stmt, alias_map=current_map)
                if bound_aliases is not None:
                    current_map = bound_aliases
                    index += 1
                    continue
                if isinstance(stmt, ast.Return):
                    return _resolve_alias_expression(stmt.value, alias_map=current_map)
                if isinstance(stmt, ast.If):
                    tail = list(stmts[index + 1 :])
                    body_expr = _resolve_return_expression(
                        list(stmt.body) + tail,
                        alias_map=dict(current_map),
                        depth=depth + 1,
                    )
                    orelse_expr = _resolve_return_expression(
                        list(stmt.orelse) + tail,
                        alias_map=dict(current_map),
                        depth=depth + 1,
                    )
                    if body_expr is None or orelse_expr is None:
                        return None
                    if ast.dump(body_expr, include_attributes=False) == ast.dump(orelse_expr, include_attributes=False):
                        return body_expr
                    return ast.IfExp(
                        test=copy.deepcopy(stmt.test),
                        body=body_expr,
                        orelse=orelse_expr,
                    )
                if isinstance(stmt, ast.Pass):
                    index += 1
                    continue
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    index += 1
                    continue
                return None
            return None

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = list(node.body)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            if not body:
                continue
            resolved_return = _resolve_return_expression(body, alias_map={})
            if resolved_return is None:
                continue
            params = [item.arg for item in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]]
            function_meta[node.name] = (params, resolved_return)

        def _resolve_call_argument(call: ast.Call, *, index: int, param_name: str) -> ast.AST | None:
            if index < len(call.args):
                return call.args[index]
            for keyword in call.keywords:
                if keyword.arg == param_name:
                    return keyword.value
            return None

        def _passthrough_param_names(
            expr: ast.AST | None,
            *,
            params: list[str],
            known_wrappers: dict[str, set[tuple[int, str]]],
            known_module_wrappers: dict[str, dict[str, set[tuple[int, str]]]],
            depth: int = 0,
        ) -> set[str]:
            if depth > 8 or expr is None:
                return set()
            if isinstance(expr, ast.Name):
                return {expr.id} if expr.id in params else set()
            if isinstance(expr, ast.IfExp):
                body_params = _passthrough_param_names(
                    expr.body,
                    params=params,
                    known_wrappers=known_wrappers,
                    known_module_wrappers=known_module_wrappers,
                    depth=depth + 1,
                )
                else_params = _passthrough_param_names(
                    expr.orelse,
                    params=params,
                    known_wrappers=known_wrappers,
                    known_module_wrappers=known_module_wrappers,
                    depth=depth + 1,
                )
                if not body_params or not else_params:
                    return set()
                return body_params.union(else_params)
            if isinstance(expr, ast.Call):
                callee_entries: set[tuple[int, str]] | None = None
                if isinstance(expr.func, ast.Name):
                    callee_entries = known_wrappers.get(expr.func.id)
                elif isinstance(expr.func, ast.Attribute) and isinstance(expr.func.value, ast.Name):
                    module_alias = expr.func.value.id
                    callee_entries = known_module_wrappers.get(module_alias, {}).get(expr.func.attr)
                if not callee_entries:
                    return set()
                output: set[str] = set()
                for idx, param_name in callee_entries:
                    passed = _resolve_call_argument(expr, index=idx, param_name=param_name)
                    if passed is None:
                        return set()
                    passed_params = _passthrough_param_names(
                        passed,
                        params=params,
                        known_wrappers=known_wrappers,
                        known_module_wrappers=known_module_wrappers,
                        depth=depth + 1,
                    )
                    if not passed_params:
                        return set()
                    output.update(passed_params)
                return output
            return set()

        changed = True
        while changed:
            changed = False
            for name, (params, returned_expr) in function_meta.items():
                passthrough_params = _passthrough_param_names(
                    returned_expr,
                    params=params,
                    known_wrappers=wrappers,
                    known_module_wrappers=module_wrappers,
                )
                if not passthrough_params:
                    continue
                entries = {(idx, param) for idx, param in enumerate(params) if param in passthrough_params}
                if not entries:
                    continue
                existing = wrappers.get(name, set())
                merged = set(existing).union(entries)
                if merged != existing:
                    wrappers[name] = merged
                    changed = True
        return wrappers

    def _collect_imported_passthrough_wrappers(
        self,
        *,
        source: str,
    ) -> tuple[dict[str, set[tuple[int, str]]], dict[str, dict[str, set[tuple[int, str]]]]]:
        direct_wrappers: dict[str, set[tuple[int, str]]] = {}
        module_wrappers: dict[str, dict[str, set[tuple[int, str]]]] = {}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return direct_wrappers, module_wrappers

        module_cache: dict[str, dict[str, set[tuple[int, str]]]] = {}

        def _wrappers_for_module(module_name: str, *, depth: int = 0) -> dict[str, set[tuple[int, str]]]:
            raw_name = str(module_name or "").strip()
            if not raw_name or depth > 6:
                return {}
            cached = module_cache.get(raw_name)
            if cached is not None:
                return cached
            module_cache[raw_name] = {}
            module_path = self._module_path_for_name(raw_name)
            if module_path is None:
                return {}
            module_source = module_path.read_text(encoding="utf-8", errors="ignore")
            try:
                module_tree = ast.parse(module_source)
            except SyntaxError:
                return {}
            seed_wrappers: dict[str, set[tuple[int, str]]] = {}
            seed_module_wrappers: dict[str, dict[str, set[tuple[int, str]]]] = {}
            for module_node in ast.walk(module_tree):
                if isinstance(module_node, ast.ImportFrom):
                    if int(module_node.level) != 0:
                        continue
                    imported_module_name = str(module_node.module or "").strip()
                    if not imported_module_name:
                        continue
                    imported_wrappers = _wrappers_for_module(imported_module_name, depth=depth + 1)
                    if not imported_wrappers:
                        continue
                    for alias in module_node.names:
                        imported_name = str(alias.name or "").strip()
                        if not imported_name or imported_name == "*":
                            continue
                        local_name = str(alias.asname or imported_name).strip()
                        if not local_name:
                            continue
                        imported_entries = imported_wrappers.get(imported_name, set())
                        if not imported_entries:
                            continue
                        merged_entries = set(seed_wrappers.get(local_name, set()))
                        merged_entries.update(imported_entries)
                        seed_wrappers[local_name] = merged_entries
                    continue
                if isinstance(module_node, ast.Import):
                    for alias in module_node.names:
                        imported_module_name = str(alias.name or "").strip()
                        if not imported_module_name:
                            continue
                        imported_wrappers = _wrappers_for_module(imported_module_name, depth=depth + 1)
                        if not imported_wrappers:
                            continue
                        local_name = str(alias.asname or imported_module_name.split(".")[0]).strip()
                        if not local_name:
                            continue
                        merged_module_entries = {
                            key: set(value)
                            for key, value in seed_module_wrappers.get(local_name, {}).items()
                        }
                        for wrapper_name, entries in imported_wrappers.items():
                            merged = set(merged_module_entries.get(wrapper_name, set()))
                            merged.update(entries)
                            merged_module_entries[wrapper_name] = merged
                        seed_module_wrappers[local_name] = merged_module_entries
            parsed_wrappers = self._collect_parameter_passthrough_wrappers(
                module_tree,
                seed_wrappers=seed_wrappers,
                seed_module_wrappers=seed_module_wrappers,
            )
            module_cache[raw_name] = parsed_wrappers
            return parsed_wrappers

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if int(node.level) != 0:
                    continue
                raw_module = str(node.module or "").strip()
                if not raw_module:
                    continue
                imported_wrappers = _wrappers_for_module(raw_module)
                if not imported_wrappers:
                    continue
                for alias in node.names:
                    raw_name = str(alias.name or "").strip()
                    if not raw_name or raw_name == "*":
                        continue
                    local_name = str(alias.asname or raw_name).strip()
                    if not local_name:
                        continue
                    entries = imported_wrappers.get(raw_name)
                    if not entries:
                        continue
                    existing = direct_wrappers.get(local_name, set())
                    direct_wrappers[local_name] = set(existing).union(entries)
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    raw_module = str(alias.name or "").strip()
                    if not raw_module:
                        continue
                    imported_wrappers = _wrappers_for_module(raw_module)
                    if not imported_wrappers:
                        continue
                    local_name = str(alias.asname or raw_module.split(".")[0]).strip()
                    if not local_name:
                        continue
                    existing_module = module_wrappers.get(local_name, {})
                    merged_module: dict[str, set[tuple[int, str]]] = {
                        key: set(value)
                        for key, value in existing_module.items()
                    }
                    for wrapper_name, entries in imported_wrappers.items():
                        merged_existing = merged_module.get(wrapper_name, set())
                        merged_module[wrapper_name] = set(merged_existing).union(entries)
                    module_wrappers[local_name] = merged_module
        return direct_wrappers, module_wrappers

    @staticmethod
    def _find_constructor_aliases_from_source(
        *,
        source: str,
        class_name: str,
        extra_factory_names: set[str] | None = None,
        extra_module_factory_attrs: dict[str, set[str]] | None = None,
        extra_passthrough_wrappers: dict[str, set[tuple[int, str]]] | None = None,
        extra_module_passthrough_wrappers: dict[str, dict[str, set[tuple[int, str]]]] | None = None,
    ) -> set[str]:
        aliases: set[str] = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return aliases
        factory_names = set(
            SemanticRefactorFallback._collect_simple_constructor_factories(
                tree=tree,
                class_name=class_name,
                seed_factory_names=extra_factory_names,
                seed_module_factory_attrs=extra_module_factory_attrs,
            )
        )
        if extra_factory_names:
            factory_names.update(str(name) for name in extra_factory_names if str(name).strip())
        passthrough_wrappers = SemanticRefactorFallback._collect_parameter_passthrough_wrappers(tree)
        if extra_passthrough_wrappers:
            for wrapper_name, wrapper_entries in extra_passthrough_wrappers.items():
                name = str(wrapper_name or "").strip()
                if not name:
                    continue
                existing_entries = passthrough_wrappers.get(name, set())
                passthrough_wrappers[name] = set(existing_entries).union(wrapper_entries)
        assignments: list[tuple[list[str], ast.AST]] = []
        for node in ast.walk(tree):
            value: ast.AST | None = None
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                value = node.value
                for raw_target in node.targets:
                    targets.extend(SemanticRefactorFallback._extract_name_targets(raw_target))
            elif isinstance(node, ast.AnnAssign):
                value = node.value
                targets = SemanticRefactorFallback._extract_name_targets(node.target)
            if value is None:
                continue
            assignments.append((targets, value))

        def _resolve_call_argument(call: ast.Call, *, arg_index: int, param_name: str) -> ast.AST | None:
            candidate_arg: ast.AST | None = call.args[arg_index] if arg_index < len(call.args) else None
            if candidate_arg is not None:
                return candidate_arg
            for keyword in call.keywords:
                if keyword.arg == param_name:
                    return keyword.value
            return None

        def _is_safe_passthrough_call(
            *,
            call: ast.Call,
            passthrough_entries: set[tuple[int, str]],
            depth: int,
        ) -> bool:
            for arg_index, param_name in passthrough_entries:
                passthrough_arg = _resolve_call_argument(call, arg_index=arg_index, param_name=param_name)
                if passthrough_arg is None:
                    return False
                if not _is_safe_value(passthrough_arg, depth=depth + 1):
                    return False
            return True

        def _is_safe_call(call: ast.Call, *, depth: int) -> bool:
            if depth > 6:
                return False
            if isinstance(call.func, ast.Name):
                callee = call.func.id
                if callee == class_name or callee in factory_names:
                    return True
                passthrough_entries = passthrough_wrappers.get(callee)
                if not passthrough_entries:
                    return False
                return _is_safe_passthrough_call(
                    call=call,
                    passthrough_entries=passthrough_entries,
                    depth=depth,
                )
            if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                module_alias = call.func.value.id
                if extra_module_passthrough_wrappers:
                    module_entries = extra_module_passthrough_wrappers.get(module_alias, {})
                    passthrough_entries = module_entries.get(call.func.attr, set())
                    if passthrough_entries:
                        return _is_safe_passthrough_call(
                            call=call,
                            passthrough_entries=passthrough_entries,
                            depth=depth,
                        )
                if extra_module_factory_attrs:
                    allowed_attrs = extra_module_factory_attrs.get(module_alias, set())
                    return call.func.attr in allowed_attrs
                return False
            return False

        def _is_safe_value(value: ast.AST, *, depth: int) -> bool:
            if depth > 6:
                return False
            if isinstance(value, ast.Name):
                return value.id in aliases
            if isinstance(value, ast.Call):
                return _is_safe_call(value, depth=depth + 1)
            if isinstance(value, ast.IfExp):
                return _is_safe_value(value.body, depth=depth + 1) and _is_safe_value(value.orelse, depth=depth + 1)
            return False

        changed = True
        while changed:
            changed = False
            for targets, value in assignments:
                if not targets:
                    continue
                if not _is_safe_value(value, depth=0):
                    continue
                for target in targets:
                    if target in aliases:
                        continue
                    aliases.add(target)
                    changed = True
        return aliases

    @staticmethod
    def _has_attribute_calls_for_symbol(*, source: str, symbol_name: str) -> bool:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return True
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr == symbol_name:
                return True
        return False

    @staticmethod
    def _strip_common_indent(lines: list[str], *, indent: int) -> list[str]:
        if indent <= 0:
            return list(lines)
        prefix = " " * indent
        stripped: list[str] = []
        for line in lines:
            if not line.strip():
                stripped.append("")
                continue
            if line.startswith(prefix):
                stripped.append(line[indent:])
                continue
            stripped.append(line.lstrip(" "))
        return stripped

    @staticmethod
    def _atomic_write_texts(writes: dict[Path, str]) -> None:
        originals: dict[Path, str | None] = {}
        for path in writes:
            originals[path] = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else None
        try:
            for path, text in writes.items():
                path.write_text(text, encoding="utf-8")
        except Exception as exc:
            for path, original in originals.items():
                try:
                    if original is None:
                        if path.exists():
                            path.unlink()
                    else:
                        path.write_text(original, encoding="utf-8")
                except Exception:
                    pass
            raise RuntimeError(f"move_atomic_write_failed: {exc}") from exc

    def _apply_move(
        self,
        *,
        target: Path,
        move_target: Path | None,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        apply: bool,
        reason: str,
    ) -> dict[str, Any]:
        _ = end_character
        if move_target is None:
            return _failure(kind="move", reason="move_target_path_required", apply=apply)
        if move_target == target:
            return _failure(kind="move", reason="move_target_same_as_source", apply=apply)
        if move_target.suffix != ".py":
            return _failure(kind="move", reason="move_target_must_be_python_file", apply=apply)
        if not move_target.exists() or not move_target.is_file():
            return _failure(kind="move", reason="move_target_not_found", apply=apply)

        source = target.read_text(encoding="utf-8", errors="ignore")
        target_source = move_target.read_text(encoding="utf-8", errors="ignore")
        try:
            source_tree = ast.parse(source)
        except SyntaxError:
            return _failure(kind="move", reason="source_parse_failed", apply=apply)
        try:
            ast.parse(target_source)
        except SyntaxError:
            return _failure(kind="move", reason="move_target_invalid_python", apply=apply)

        source_lines = source.splitlines()
        span = self._resolve_line_span(lines=source_lines, start_line=start_line, end_line=end_line, end_character=end_character)
        if span is None:
            return _failure(kind="move", reason="invalid_range", apply=apply)
        start, end = span
        start_line_1based = start + 1
        end_line_1based = end + 1

        movable_node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None
        owner_class: ast.ClassDef | None = None
        method_move_kind: str | None = None

        method_selection_requested = int(start_character) > 0
        # Prefer nested method selection over selecting the whole class when
        # caller selected from an indented position.
        if method_selection_requested:
            for node in source_tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                for member in node.body:
                    if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    node_start, node_end = self._node_span_lines(member)
                    if node_end < start_line_1based or node_start > end_line_1based:
                        continue
                    if node_start <= 0 or node_end < node_start:
                        continue
                    if max(node_start, start_line_1based) > min(node_end, end_line_1based):
                        continue
                    # Method-level move should only trigger when selection starts at
                    # method (or decorator) lines, not class declaration lines.
                    if start_line_1based < node_start:
                        continue
                    if any(self._decorator_is_staticmethod(item) for item in member.decorator_list):
                        method_move_kind = "staticmethod"
                    elif any(self._decorator_is_classmethod(item) for item in member.decorator_list):
                        method_move_kind = "classmethod"
                    elif not member.decorator_list:
                        method_move_kind = "instancemethod"
                    else:
                        continue
                    movable_node = member
                    owner_class = node
                    break
                if movable_node is not None:
                    break

        if movable_node is None:
            for node in source_tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                node_start, node_end = self._node_span_lines(node)
                if node_end < start_line_1based or node_start > end_line_1based:
                    continue
                if node_start <= 0 or node_end < node_start:
                    continue
                # Prefer the top-level symbol that overlaps the requested range.
                if max(node_start, start_line_1based) <= min(node_end, end_line_1based):
                    movable_node = node
                    break
        if movable_node is None:
            return _failure(kind="move", reason="move_selection_not_supported", apply=apply)

        node_start, node_end = self._node_span_lines(movable_node)
        if node_start <= 0 or node_end < node_start:
            return _failure(kind="move", reason="move_node_position_missing", apply=apply)

        moved_lines = source_lines[node_start - 1 : node_end]
        if not moved_lines:
            return _failure(kind="move", reason="move_selection_empty", apply=apply)

        remaining_lines = source_lines[: node_start - 1] + source_lines[node_end:]
        moved_name = str(movable_node.name)
        if method_move_kind is not None:
            if owner_class is None:
                return _failure(kind="move", reason="move_selection_not_supported", apply=apply)
            if not isinstance(movable_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return _failure(kind="move", reason="move_selection_not_supported", apply=apply)

            method_clone = copy.deepcopy(movable_node)
            if method_move_kind == "staticmethod":
                method_clone.decorator_list = [
                    item for item in method_clone.decorator_list if not self._decorator_is_staticmethod(item)
                ]
            elif method_move_kind == "classmethod":
                method_clone.decorator_list = [
                    item for item in method_clone.decorator_list if not self._decorator_is_classmethod(item)
                ]
                arg_container: list[ast.arg] | None = None
                if method_clone.args.args:
                    arg_container = method_clone.args.args
                elif method_clone.args.posonlyargs:
                    arg_container = method_clone.args.posonlyargs
                if not arg_container:
                    return _failure(kind="move", reason="move_classmethod_missing_cls_param", apply=apply)
                cls_param = str(arg_container[0].arg)
                if self._function_uses_name(movable_node, cls_param):
                    return _failure(kind="move", reason="move_classmethod_uses_cls_state", apply=apply)
                del arg_container[0]
            elif method_move_kind == "instancemethod":
                if method_clone.decorator_list:
                    return _failure(kind="move", reason="move_selection_not_supported", apply=apply)
                arg_container: list[ast.arg] | None = None
                if method_clone.args.args:
                    arg_container = method_clone.args.args
                elif method_clone.args.posonlyargs:
                    arg_container = method_clone.args.posonlyargs
                if not arg_container:
                    return _failure(kind="move", reason="move_instance_method_missing_self_param", apply=apply)
                self_param = str(arg_container[0].arg)
                if self._function_uses_name(movable_node, self_param):
                    return _failure(kind="move", reason="move_instance_method_uses_instance_state", apply=apply)
                del arg_container[0]
            else:
                return _failure(kind="move", reason="move_selection_not_supported", apply=apply)

            moved_block = ast.unparse(method_clone).strip()
            if not moved_block:
                return _failure(kind="move", reason="move_selection_empty", apply=apply)
            moved_block = f"{moved_block}\n"

            remaining_members = [item for item in owner_class.body if item is not movable_node]
            if not remaining_members:
                class_indent = _leading_spaces(source_lines[int(owner_class.lineno) - 1])
                pass_line = f"{' ' * (class_indent + 4)}pass"
                remaining_lines = source_lines[: node_start - 1] + [pass_line] + source_lines[node_end:]
        else:
            moved_block = self._build_text_from_lines(lines=moved_lines, trailing_newline=True)
        updated_source = self._build_text_from_lines(lines=remaining_lines, trailing_newline=source.endswith("\n"))

        if method_move_kind in {"staticmethod", "classmethod"} and owner_class is not None:
            updated_source = re.sub(
                rf"\b{re.escape(owner_class.name)}\s*\.\s*{re.escape(moved_name)}\s*\(",
                f"{moved_name}(",
                updated_source,
            )
        if method_move_kind == "instancemethod" and owner_class is not None:
            updated_source = re.sub(
                rf"\b{re.escape(owner_class.name)}\s*\(\s*\)\s*\.\s*{re.escape(moved_name)}\s*\(",
                f"{moved_name}(",
                updated_source,
            )
            updated_source = re.sub(
                rf"\b{re.escape(owner_class.name)}\s*\([^\n]*?\)\s*\.\s*{re.escape(moved_name)}\s*\(",
                f"{moved_name}(",
                updated_source,
            )
            aliases = self._find_constructor_aliases_from_source(source=updated_source, class_name=owner_class.name)
            for alias in sorted(aliases, key=len, reverse=True):
                updated_source = re.sub(
                    rf"\b{re.escape(alias)}\s*\.\s*{re.escape(moved_name)}\s*\(",
                    f"{moved_name}(",
                    updated_source,
                )
            if self._has_attribute_calls_for_symbol(source=updated_source, symbol_name=moved_name):
                return _failure(kind="move", reason="move_instance_method_unresolved_callsites", apply=apply)

        cross_file_writes: dict[Path, str] = {}
        if method_move_kind is not None and owner_class is not None:
            source_module_name = self._module_name_for_path(target)
            source_factory_names = self._collect_simple_constructor_factories(
                tree=source_tree,
                class_name=owner_class.name,
            )
            for candidate in self.root.rglob("*.py"):
                candidate_path = candidate.expanduser().resolve()
                if candidate_path in {target, move_target}:
                    continue
                if not candidate_path.is_file():
                    continue
                candidate_source = candidate_path.read_text(encoding="utf-8", errors="ignore")
                if owner_class.name not in candidate_source and f".{moved_name}" not in candidate_source:
                    continue
                try:
                    ast.parse(candidate_source)
                except SyntaxError:
                    continue
                candidate_updated = candidate_source
                if method_move_kind in {"staticmethod", "classmethod"}:
                    candidate_updated = re.sub(
                        rf"\b{re.escape(owner_class.name)}\s*\.\s*{re.escape(moved_name)}\s*\(",
                        f"{moved_name}(",
                        candidate_updated,
                    )
                elif method_move_kind == "instancemethod":
                    candidate_updated = re.sub(
                        rf"\b{re.escape(owner_class.name)}\s*\([^\n]*?\)\s*\.\s*{re.escape(moved_name)}\s*\(",
                        f"{moved_name}(",
                        candidate_updated,
                    )
                    imported_symbols: set[str] = set()
                    imported_module_aliases: set[str] = set()
                    if source_module_name:
                        imported_symbols = self._imported_symbols_from_module(
                            source=candidate_updated,
                            module_name=source_module_name,
                        )
                        imported_module_aliases = self._imported_module_aliases_from_module(
                            source=candidate_updated,
                            module_name=source_module_name,
                        )
                    imported_factory_names = set(source_factory_names).intersection(imported_symbols)
                    imported_module_factory_attrs = {
                        alias: set(source_factory_names)
                        for alias in imported_module_aliases
                    }
                    imported_wrapper_names, imported_module_wrapper_entries = self._collect_imported_passthrough_wrappers(
                        source=candidate_updated,
                    )
                    for factory_name in sorted(imported_factory_names, key=len, reverse=True):
                        candidate_updated = re.sub(
                            rf"\b{re.escape(factory_name)}\s*\([^\n]*?\)\s*\.\s*{re.escape(moved_name)}\s*\(",
                            f"{moved_name}(",
                            candidate_updated,
                        )
                    for module_alias, factory_names in imported_module_factory_attrs.items():
                        for factory_name in sorted(factory_names, key=len, reverse=True):
                            candidate_updated = re.sub(
                                rf"\b{re.escape(module_alias)}\s*\.\s*{re.escape(factory_name)}\s*\([^\n]*?\)\s*\.\s*{re.escape(moved_name)}\s*\(",
                                f"{moved_name}(",
                                candidate_updated,
                            )
                    candidate_aliases = self._find_constructor_aliases_from_source(
                        source=candidate_updated,
                        class_name=owner_class.name,
                        extra_factory_names=imported_factory_names,
                        extra_module_factory_attrs=imported_module_factory_attrs,
                        extra_passthrough_wrappers=imported_wrapper_names,
                        extra_module_passthrough_wrappers=imported_module_wrapper_entries,
                    )
                    for alias in sorted(candidate_aliases, key=len, reverse=True):
                        candidate_updated = re.sub(
                            rf"\b{re.escape(alias)}\s*\.\s*{re.escape(moved_name)}\s*\(",
                            f"{moved_name}(",
                            candidate_updated,
                        )
                if candidate_updated == candidate_source:
                    continue
                module_name = self._module_name_for_path(move_target)
                if not module_name:
                    return _failure(kind="move", reason="move_target_outside_workspace_root", apply=apply)
                candidate_updated = self._ensure_import_line(
                    source=candidate_updated,
                    module_name=module_name,
                    symbol_name=moved_name,
                )
                try:
                    ast.parse(candidate_updated)
                except SyntaxError:
                    return _failure(kind="move", reason="move_cross_file_generated_invalid_python", apply=apply)
                if candidate_updated != candidate_source:
                    cross_file_writes[candidate_path] = candidate_updated

        updated_target = self._append_python_block(existing=target_source, block=moved_block)

        if re.search(rf"\b{re.escape(moved_name)}\b", updated_source):
            module_name = self._module_name_for_path(move_target)
            if not module_name:
                return _failure(kind="move", reason="move_target_outside_workspace_root", apply=apply)
            updated_source = self._ensure_import_line(
                source=updated_source,
                module_name=module_name,
                symbol_name=moved_name,
            )

        try:
            if updated_source.strip():
                ast.parse(updated_source)
            ast.parse(updated_target)
        except SyntaxError:
            return _failure(kind="move", reason="move_generated_invalid_python", apply=apply)

        changed_source = updated_source != source
        changed_target = updated_target != target_source
        changed_cross_files = bool(cross_file_writes)
        if not changed_source and not changed_target and not changed_cross_files:
            return _failure(kind="move", reason="move_no_changes", apply=apply)

        if apply:
            try:
                writes: dict[Path, str] = {
                    target: updated_source,
                    move_target: updated_target,
                }
                writes.update(cross_file_writes)
                self._atomic_write_texts(writes)
            except RuntimeError as exc:
                return _failure(kind="move", reason=str(exc), apply=apply)

        changes: list[dict[str, Any]] = []
        if changed_source:
            changes.append({"path": str(target), "occurrences": 1, "source": "semantic_fallback"})
        if changed_target:
            changes.append({"path": str(move_target), "occurrences": 1, "source": "semantic_fallback"})
        for path in sorted(cross_file_writes):
            changes.append({"path": str(path), "occurrences": 1, "source": "semantic_fallback"})

        selected_payload = {
            "title": "Fallback move symbol",
            "kind": None,
            "normalized_kind": "move",
            "source": "semantic_fallback",
        }
        return {
            "backend": "semantic_fallback",
            "applied": bool(apply and (changed_source or changed_target)),
            "selected": selected_payload,
            "files_changed": len(changes),
            "occurrences": sum(int(item["occurrences"]) for item in changes),
            "changes": changes,
            "fallback_attempted": True,
            "fallback_kind": "move",
            "fallback_reason": reason,
            "fallback_error": "",
            "fallback_apply_requested": bool(apply),
        }

    def _apply_extract(
        self,
        *,
        target: Path,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        apply: bool,
        reason: str,
    ) -> dict[str, Any]:
        _ = start_character
        source = target.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()
        span = self._resolve_line_span(lines=lines, start_line=start_line, end_line=end_line, end_character=end_character)
        if span is None:
            return _failure(kind="extract", reason="invalid_range", apply=apply)
        start, end = span
        selected = lines[start : end + 1]
        if not selected or all(not line.strip() for line in selected):
            return _failure(kind="extract", reason="empty_selection", apply=apply)

        function_node = self._find_containing_function(
            source=source,
            start_line_1based=start + 1,
            end_line_1based=end + 1,
        )
        if function_node is None:
            return _failure(kind="extract", reason="selection_not_in_function", apply=apply)

        function_def_line = lines[max(0, int(function_node.lineno) - 1)]
        function_indent = _leading_spaces(function_def_line)
        selected_indent = _leading_spaces(selected[0])
        if selected_indent <= function_indent:
            return _failure(kind="extract", reason="selection_must_be_function_body", apply=apply)

        dedented: list[str] = []
        for line in selected:
            if not line.strip():
                dedented.append("")
                continue
            if not line.startswith(" " * selected_indent):
                return _failure(kind="extract", reason="inconsistent_indentation", apply=apply)
            dedented.append(line[selected_indent:])

        helper_indent = " " * selected_indent
        helper_name = f"_extracted_{function_node.name}_{start + 1}"
        helper_header = f"{helper_indent}def {helper_name}():"
        helper_body: list[str] = []
        for line in dedented:
            if line:
                helper_body.append(f"{helper_indent}    {line}")
            else:
                helper_body.append("")

        has_return = any(re.match(r"^\s*return\b", line) for line in selected)
        replacement_line = f"{helper_indent}return {helper_name}()" if has_return else f"{helper_indent}{helper_name}()"

        updated_lines = lines[:start] + [helper_header] + helper_body + [""] + [replacement_line] + lines[end + 1 :]
        updated = "\n".join(updated_lines) + ("\n" if source.endswith("\n") or updated_lines else "")

        try:
            ast.parse(updated)
        except SyntaxError:
            return _failure(kind="extract", reason="fallback_generated_invalid_syntax", apply=apply)

        changed = updated != source
        if apply and changed:
            target.write_text(updated, encoding="utf-8")

        selected_payload = {
            "title": "Fallback extract function",
            "kind": None,
            "normalized_kind": "extract",
            "source": "semantic_fallback",
        }
        changes = [{"path": str(target), "occurrences": 1, "source": "semantic_fallback"}] if changed else []
        return {
            "backend": "semantic_fallback",
            "applied": bool(apply and changed),
            "selected": selected_payload,
            "files_changed": 1 if changed else 0,
            "occurrences": 1 if changed else 0,
            "changes": changes,
            "fallback_attempted": True,
            "fallback_kind": "extract",
            "fallback_reason": reason,
            "fallback_error": "",
            "fallback_apply_requested": bool(apply),
        }

    def _apply_inline(
        self,
        *,
        target: Path,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        apply: bool,
        reason: str,
    ) -> dict[str, Any]:
        source = target.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()
        span = self._resolve_line_span(lines=lines, start_line=start_line, end_line=end_line, end_character=end_character)
        if span is None:
            return _failure(kind="inline", reason="invalid_range", apply=apply)
        start, end = span
        start_line_1based = start + 1
        end_line_1based = end + 1

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return _failure(kind="inline", reason="source_parse_failed", apply=apply)

        candidate_calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            node_start = int(getattr(node, "lineno", 0))
            node_end = int(getattr(node, "end_lineno", node_start))
            if node_end < start_line_1based or node_start > end_line_1based:
                continue
            candidate_calls.append(node)
        if not candidate_calls:
            return _failure(kind="inline", reason="inline_call_not_found", apply=apply)
        candidate_calls.sort(key=lambda item: (int(getattr(item, "lineno", 0)), int(getattr(item, "col_offset", 0))))
        call = candidate_calls[0]

        if not isinstance(call.func, ast.Name):
            return _failure(kind="inline", reason="inline_unsupported_call_target", apply=apply)
        function_name = str(call.func.id)

        function_def: ast.FunctionDef | None = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                function_def = node
                break
        if function_def is None:
            return _failure(kind="inline", reason="inline_function_definition_not_found", apply=apply)

        function_body = list(function_def.body)
        if (
            function_body
            and isinstance(function_body[0], ast.Expr)
            and isinstance(function_body[0].value, ast.Constant)
            and isinstance(function_body[0].value.value, str)
        ):
            function_body = function_body[1:]
        if len(function_body) != 1 or not isinstance(function_body[0], ast.Return) or function_body[0].value is None:
            return _failure(kind="inline", reason="inline_function_body_not_supported", apply=apply)

        args_spec = function_def.args
        if (
            args_spec.vararg is not None
            or args_spec.kwarg is not None
            or args_spec.kwonlyargs
            or args_spec.defaults
            or args_spec.kw_defaults
            or args_spec.posonlyargs
        ):
            return _failure(kind="inline", reason="inline_function_signature_not_supported", apply=apply)
        if call.keywords:
            return _failure(kind="inline", reason="inline_call_keywords_not_supported", apply=apply)

        param_names = [arg.arg for arg in args_spec.args]
        if len(param_names) != len(call.args):
            return _failure(kind="inline", reason="inline_argument_count_mismatch", apply=apply)
        bindings: dict[str, ast.AST] = {
            name: copy.deepcopy(value) for name, value in zip(param_names, call.args, strict=True)
        }

        class _SubstituteParameters(ast.NodeTransformer):
            def __init__(self, mapping: dict[str, ast.AST]) -> None:
                self.mapping = mapping

            def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
                if isinstance(node.ctx, ast.Load) and node.id in self.mapping:
                    return copy.deepcopy(self.mapping[node.id])
                return node

        return_expr = copy.deepcopy(function_body[0].value)
        inlined_expr = _SubstituteParameters(bindings).visit(return_expr)
        ast.fix_missing_locations(inlined_expr)
        inlined_text = ast.unparse(inlined_expr).strip()
        if not inlined_text:
            return _failure(kind="inline", reason="inline_expression_empty", apply=apply)

        call_start_line = int(getattr(call, "lineno", 0))
        call_end_line = int(getattr(call, "end_lineno", call_start_line))
        call_start_character = int(getattr(call, "col_offset", -1))
        call_end_character = int(getattr(call, "end_col_offset", -1))
        if call_start_line <= 0 or call_end_line <= 0 or call_start_character < 0 or call_end_character < 0:
            return _failure(kind="inline", reason="inline_call_position_missing", apply=apply)

        start_offset = self._position_to_offset(
            source,
            line_1based=call_start_line,
            character=call_start_character,
        )
        end_offset = self._position_to_offset(
            source,
            line_1based=call_end_line,
            character=call_end_character,
        )
        if end_offset < start_offset:
            return _failure(kind="inline", reason="inline_invalid_call_offsets", apply=apply)

        updated = f"{source[:start_offset]}{inlined_text}{source[end_offset:]}"
        try:
            ast.parse(updated)
        except SyntaxError:
            return _failure(kind="inline", reason="inline_generated_invalid_syntax", apply=apply)

        changed = updated != source
        if apply and changed:
            target.write_text(updated, encoding="utf-8")

        selected_payload = {
            "title": "Fallback inline function",
            "kind": None,
            "normalized_kind": "inline",
            "source": "semantic_fallback",
        }
        changes = [{"path": str(target), "occurrences": 1, "source": "semantic_fallback"}] if changed else []
        return {
            "backend": "semantic_fallback",
            "applied": bool(apply and changed),
            "selected": selected_payload,
            "files_changed": 1 if changed else 0,
            "occurrences": 1 if changed else 0,
            "changes": changes,
            "fallback_attempted": True,
            "fallback_kind": "inline",
            "fallback_reason": reason,
            "fallback_error": "",
            "fallback_apply_requested": bool(apply),
        }
