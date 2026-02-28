from __future__ import annotations
from enum import Enum, auto
from typing import List, Tuple, Optional
from dataclasses import dataclass


class TK(Enum):
    EOF = auto()
    NAME = auto()
    NUMBER = auto()
    STRING = auto()
    KEYWORD = auto()
    OP = auto()
    COMMENT = auto()
    LONG_COMMENT = auto()
    LONG_STRING = auto()
    NEWLINE = auto()
    WS = auto()


KEYWORDS = frozenset({
    'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for',
    'function', 'goto', 'if', 'in', 'local', 'nil', 'not', 'or',
    'repeat', 'return', 'then', 'true', 'until', 'while', 'continue',
})

MULTI_OPS_3 = frozenset({'...', '//='})
MULTI_OPS_2 = frozenset({
    '==', '~=', '<=', '>=', '..', '//', '->', '+=', '-=', '*=',
    '/=', '%=', '^=', '..=', '::', '&&', '||', '<<', '>>',
})


@dataclass
class Token:
    kind: TK
    value: str
    line: int = 1
    col: int = 1


def tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    n = len(source)
    line = 1
    col = 1

    def _advance(count=1):
        nonlocal i, line, col
        for _ in range(count):
            if i < n and source[i] == '\n':
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    def _peek(offset=0):
        p = i + offset
        return source[p] if p < n else ''

    def _match_long_bracket():
        if _peek() != '[':
            return None
        j = i + 1
        eq_count = 0
        while j < n and source[j] == '=':
            eq_count += 1
            j += 1
        if j < n and source[j] == '[':
            close = ']' + '=' * eq_count + ']'
            end = source.find(close, j + 1)
            if end == -1:
                return source[i:n], n - i
            return source[i:end + len(close)], end + len(close) - i
        return None

    while i < n:
        ch = source[i]
        start_line, start_col = line, col

        if ch == '-' and _peek(1) == '-':
            if _peek(2) == '[':
                old_i = i
                _advance(2)
                lb = _match_long_bracket()
                if lb is not None:
                    text, length = lb
                    full = '--' + text
                    _advance(length)
                    tokens.append(Token(TK.LONG_COMMENT, full, start_line, start_col))
                    continue
                else:
                    i = old_i

            start = i
            _advance(2)
            while i < n and source[i] != '\n':
                _advance()
            tokens.append(Token(TK.COMMENT, source[start:i], start_line, start_col))
            continue

        if ch == '[':
            lb = _match_long_bracket()
            if lb is not None:
                text, length = lb
                _advance(length)
                tokens.append(Token(TK.LONG_STRING, text, start_line, start_col))
                continue

        if ch in ('"', "'"):
            quote = ch
            start = i
            _advance()
            while i < n:
                c = source[i]
                if c == '\\':
                    _advance(2)
                elif c == quote:
                    _advance()
                    break
                elif c == '\n':
                    break
                else:
                    _advance()
            tokens.append(Token(TK.STRING, source[start:i], start_line, start_col))
            continue

        if ch == '`':
            start = i
            _advance()
            depth = 0
            while i < n:
                c = source[i]
                if c == '\\':
                    _advance(2)
                elif c == '{' and depth == 0:
                    depth += 1
                    _advance()
                elif c == '}' and depth > 0:
                    depth -= 1
                    _advance()
                elif c == '`' and depth == 0:
                    _advance()
                    break
                else:
                    _advance()
            tokens.append(Token(TK.STRING, source[start:i], start_line, start_col))
            continue

        if ch == '\n':
            _advance()
            tokens.append(Token(TK.NEWLINE, '\n', start_line, start_col))
            continue
        if ch == '\r':
            _advance()
            if i < n and source[i] == '\n':
                _advance()
            tokens.append(Token(TK.NEWLINE, '\n', start_line, start_col))
            continue

        if ch in ' \t\f\v':
            start = i
            while i < n and source[i] in ' \t\f\v':
                _advance()
            tokens.append(Token(TK.WS, source[start:i], start_line, start_col))
            continue

        if ch.isdigit() or (ch == '.' and i + 1 < n and source[i + 1].isdigit()):
            start = i
            if ch == '0' and i + 1 < n and source[i + 1] in 'xX':
                _advance(2)
                while i < n and (source[i] in '0123456789abcdefABCDEF_'):
                    _advance()
                if i < n and source[i] == '.':
                    _advance()
                    while i < n and (source[i] in '0123456789abcdefABCDEF_'):
                        _advance()
                if i < n and source[i] in 'pP':
                    _advance()
                    if i < n and source[i] in '+-':
                        _advance()
                    while i < n and source[i].isdigit():
                        _advance()
            elif ch == '0' and i + 1 < n and source[i + 1] in 'bB':
                _advance(2)
                while i < n and source[i] in '01_':
                    _advance()
            else:
                while i < n and (source[i].isdigit() or source[i] == '_'):
                    _advance()
                if i < n and source[i] == '.':
                    if i + 1 < n and source[i + 1] == '.':
                        pass
                    else:
                        _advance()
                        while i < n and (source[i].isdigit() or source[i] == '_'):
                            _advance()
                if i < n and source[i] in 'eE':
                    _advance()
                    if i < n and source[i] in '+-':
                        _advance()
                    while i < n and (source[i].isdigit() or source[i] == '_'):
                        _advance()
            tokens.append(Token(TK.NUMBER, source[start:i], start_line, start_col))
            continue

        if ch.isalpha() or ch == '_':
            start = i
            while i < n and (source[i].isalnum() or source[i] == '_'):
                _advance()
            word = source[start:i]
            if word in KEYWORDS:
                tokens.append(Token(TK.KEYWORD, word, start_line, start_col))
            else:
                tokens.append(Token(TK.NAME, word, start_line, start_col))
            continue

        three = source[i:i + 3]
        if three in MULTI_OPS_3:
            tokens.append(Token(TK.OP, three, start_line, start_col))
            _advance(3)
            continue

        two = source[i:i + 2]
        if two in MULTI_OPS_2:
            tokens.append(Token(TK.OP, two, start_line, start_col))
            _advance(2)
            continue

        tokens.append(Token(TK.OP, ch, start_line, start_col))
        _advance()

    tokens.append(Token(TK.EOF, '', line, col))
    return tokens
