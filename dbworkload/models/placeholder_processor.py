import re
import random
import sqlparse
import datetime as dt
from typing import List, Dict, Tuple, Optional

def replace_placeholders(sql, all_schemas):
    """
    Replace placeholders in an SQL query:
    - `_` -> `%s`
    - `__more__` -> Expands based on the number of fields in VALUES (...) or IN (...)

    Returns the modified query.
    """
    #debugPrint("check")
    sql = sql.strip()
    #debugPrint(f"▶ DEBUG: stripped SQL → `{sql}`")
    table_names = extract_table_names(sql)
    #debugPrint(f"▶ DEBUG: extracted table names → {table_names}")
    if table_names is None:
        return sql
    schemas = [all_schemas[table_name] for table_name in table_names]

    def replace_values(values_match):
        cols = values_match.group(1)  # e.g. "acc_no, id"
        values_kw = values_match.group(2)  # the "VALUES" and its whitespace
        raw_vals = values_match.group(3)  # e.g. " 1,2 ) , ( 3 ,4 ) ,(5,6 "
        suffix = values_match.group(4)  # RETURNING, semicolon, or empty

        # 1) build a single–tuple placeholder
        column_names = [c.strip() for c in cols.split(",")]
        one_ph = (
            "(" + ", ".join(get_field_column(schemas, c) for c in column_names) + ")"
        )

        # 2) split on “) , (” with any amount of space
        #    This yields one entry per tuple, no matter how they've spaced it.
        tuple_segments = re.split(r"\)\s*,\s*\(", raw_vals.strip())

        count = len(tuple_segments)

        # 3) repeat your placeholder N times - adds the ability to parse multiple tuples inserting in same values clause
        all_placeholders = ", ".join([one_ph] * count)

        # 4) re-assemble
        return f"({cols}){values_kw}{all_placeholders}{suffix}"

    # Replace the entire VALUES(...) with corrected placeholders
    #debugPrint(f"▶ DEBUG: replacing VALUES(...) in SQL: {sql}")
    sql = re.sub(
        r"\((.*)\)(.*VALUES\s*)\((.*)\)(\s+RETURNING|\s*;|$)",
        replace_values,
        sql,
        flags=re.IGNORECASE,
    )

    # now for no explicit col list: insert into orders values (...)
    pattern_no_cols = re.compile(
        r"(\bINSERT\s+INTO\s+)"  # group(1) = “INSERT INTO ”
        r"([^\s(;]+)"  # group(2) = table name
        r"(\s*VALUES\s*)"  # group(3) = “VALUES”
        r"(\([^)]*\)(?:\s*,\s*\([^)]*\))*)"  # group(4) = all the (…) tuples
        r"(\s*(?:RETURNING\b[^;]*|;|$))",  # group(5) = RETURNING / semicolon / end
        re.IGNORECASE,
    )

    def replace_no_cols(m):
        table = m.group(2)
        raw_vals = m.group(4)
        suffix = m.group(5)
        # build one‐tuple placeholder from *all* columns
        one_ph = get_field_table(all_schemas, table)

        # count how many anonymized tuples came in
        count = len(re.split(r"\)\s*,\s*\(", raw_vals.strip()))

        # repeat that many times
        all_ph = ", ".join([one_ph] * count)

        return f"{m.group(1)}{table}{m.group(3)}{all_ph}{suffix}"

    sql = re.sub(pattern_no_cols, replace_no_cols, sql)

    sql = replace_tokens(sql, schemas)
    sql = extract_set_conditions(sql, schemas)
    sql = extract_system_time(sql)
    return sql


def replace_tokens(sql, schemas):
    # Parse the query
    query = sqlparse.parse(sql)[0]

    # for i, tok in enumerate(query.tokens):
    #     debugPrint(f"token #{i}: type={type(tok)} ttype={tok.ttype!r} value={tok.value!r}")
    debugPrint("replace tokens called")
    statement = ""
    query_index = 0
    # Extract where conditions from the query
    while query_index < len(query.tokens):
        token = query.tokens[query_index]
        if token.value == "SELECT":
            query_index += 1
            statement += token.value
            while (
                query_index < len(query.tokens)
                and query.tokens[query_index].is_whitespace
            ):
                query_index += 1
                statement += " "  # exhausted all whitespaces
            statement += process_select_statements(query.tokens[query_index], schemas)
            query_index += 1
        elif type(token) == sqlparse.sql.Where:
            debugPrint(f"▶ DEBUG: matched WHERE token → `{token.value}`")
            where_statement, query_index = process_where_token(
                token, schemas, query_index
            )
            statement += where_statement
        elif type(token) == sqlparse.sql.Token and token.value.strip() == "LIMIT":
            query_index += 1
            statement += token.value
            while (
                query_index < len(query.tokens)
                and query.tokens[query_index].is_whitespace
            ):
                query_index += 1
                statement += " "  # exhausted all whitespaces
            query_index += 1
            statement += str(random.randint(1, 100))
        else:
            query_index += 1
            statement += token.value
    return statement


def process_select_statements(token, schemas):
    """
    Replace two flavors of IFNULL in SELECT projections:
      1) IFNULL(sum(col), _)
      2) IFNULL(col, _)
    """
    #the sum version was already there, adding the egenric version. There might be other functions allowd in sql for here, havent come across any, can easily add here if needed
    def _replace_ifnull_sum(expr: str) -> str:
        # Match IFNULL(sum(col), _
        m = re.search(
            r"""IFNULL\s*     # IFNULL(
                          \(\s*sum\s*  # ( sum
                          \(\s*([^)]+?)\s*\)  # (col)
                          \s*,        # ,
                       """,
            expr,
            flags=re.IGNORECASE | re.VERBOSE,
        )
        if not m:
            return expr
        col = m.group(1).strip()
        ph = get_field_column(schemas, col)
        # replace the trailing ", _)" with ", <ph>)"
        return re.sub(r"(,\s*)_(\s*\))", rf"\1{ph}\2", expr)

    def _replace_ifnull_generic(expr: str) -> str:
        # Match IFNULL(col, _)
        def repl(m):
            col = m.group(1).strip()
            ph = get_field_column(schemas, col)
            return f"IFNULL({col}, {ph})"

        return re.sub(
            r"""IFNULL\s*       # IFNULL(
               \(\s*([^)]+?)\s*,\s*_  # (col, _
               \s*\)""",  # )
            repl,
            expr,
            flags=re.IGNORECASE | re.VERBOSE,
        )

    def _process(expr: str) -> str:
        # apply sum‐case first, then generic
        expr = _replace_ifnull_sum(expr)
        return _replace_ifnull_generic(expr)

    # Walk either a list of identifiers or a single token
    if isinstance(token, sqlparse.sql.IdentifierList):
        out_parts = []
        for sub in token.tokens:
            val = sub.value
            if val.strip().upper().startswith("IFNULL"):
                val = _process(val)
                sub.value = val
            out_parts.append(sub.value)
        return "".join(out_parts)

    # single‐expression case, e.g. "IFNULL(name, _) AS name"
    return _process(token.value)


def process_where_token(where_token, schemas, query_index):
    # debugPrint(
    #     f"process where token input: \n where_token:{where_token}\n schemas: {schemas} \n query index : {query_index}"
    # )
    parts = []
    index = 1  # Skip the initial "WHERE" keyword token
    while index < len(where_token.tokens):
        condition, index = extract_where_condition(where_token.tokens, index, schemas)
        parts.append(condition)
    return where_token.tokens[0].value + "".join(parts), query_index + 1


def extract_where_condition(tokens, idx, schemas):
    # debugPrint(f"extract_where_condition input: \n tokens:{tokens}\n idx: {idx} \n schemas: {schemas}")
    # debugPrint(f"\nextract where condition called focusing on token{tokens[idx]}")
    token = tokens[idx]
    if isinstance(token, sqlparse.sql.Identifier):
        # debugPrint(f"▶ DEBUG: matched IDENTIFIER token → `{token.value}`")
        return process_identifier_token(tokens, idx, schemas)
    elif token.ttype is not None and (
        token.value in [" ", "(", ")"] or token.is_keyword
    ):
        # debugPrint(f"▶ DEBUG: matched token → `{token.value}`")
        return token.value, idx + 1
    elif isinstance(token, sqlparse.sql.Comparison):
        # debugPrint(f"▶ DEBUG: matched COMPARISON token → `{token.value}`")
        return process_comparison_token(token, schemas), idx + 1
    elif isinstance(token, sqlparse.sql.Parenthesis):
        # debugPrint(f"▶ DEBUG: matched PARENTHESIS token → `{token.value}`")
        return process_parenthesis_token(token, tokens, idx, schemas)
    else:
        # Fallback for any other token types
        # debugPrint(f"▶ DEBUG: matched token → `{token.value}`")
        return token.value, idx + 1


'''def process_identifier_token(tokens, idx, schemas):
    token = tokens[idx]
    condition = token.value
    new_index = idx + 1
    while new_index < len(tokens) and tokens[new_index].is_whitespace:
        condition += " "
        new_index += 1
    if new_index < len(tokens) and tokens[new_index].value.strip().upper() == "IN":
        condition += tokens[new_index].value
        new_index += 1
        while new_index < len(tokens) and tokens[new_index].is_whitespace:
            condition += " "
            new_index += 1
        if (
            new_index < len(tokens)
            and isinstance(tokens[new_index], sqlparse.sql.Parenthesis)
            and len(tokens[new_index].tokens) > 1
            and isinstance(tokens[new_index].tokens[1], sqlparse.sql.IdentifierList)
        ):
            condition += f"({get_field_column(schemas, token.value)}, {get_field_column(schemas, token.value)})"
            return condition, new_index + 1
        elif (
            new_index < len(tokens)
            and isinstance(tokens[new_index], sqlparse.sql.Parenthesis)
            and len(tokens[new_index].tokens) > 1
            and tokens[new_index].tokens[1].is_keyword
        ):
            return (
                f"{condition}({replace_tokens(tokens[new_index].value[1:-1], schemas)})",
                new_index + 1,
            )

    if new_index < len(tokens) and tokens[new_index].value.strip().upper() == "BETWEEN":
        condition += tokens[new_index].value
        new_index += 1
        while new_index < len(tokens) and tokens[new_index].is_whitespace:
            condition += " "
            new_index += 1
        if new_index < len(tokens) and isinstance(
            tokens[new_index], sqlparse.sql.Parenthesis
        ):
            condition += f"({get_field_column(schemas, token.value)})"
            new_index += 1
            while new_index < len(tokens) and (
                tokens[new_index].is_whitespace
                or (
                    hasattr(tokens[new_index], "value")
                    and tokens[new_index].value.strip() == "AND"
                )
            ):
                condition += tokens[new_index].value
                new_index += 1
            if new_index < len(tokens) and isinstance(
                tokens[new_index], sqlparse.sql.Parenthesis
            ):
                condition += f"({get_field_column(schemas, token.value)})"
                return condition, new_index + 1
    return condition, new_index'''

def process_identifier_token(tokens, idx, schemas):
    token = tokens[idx]
    condition = token.value       # e.g. "order_date" or "acc_no"
    new_index = idx + 1

    # 1) Skip & preserve whitespace
    while new_index < len(tokens) and tokens[new_index].is_whitespace:
        condition += tokens[new_index].value
        new_index += 1

    # 2) IN ( … )  — now supports any number of items, random number of values to choose from
    if new_index < len(tokens) and tokens[new_index].value.strip().upper() == "IN":
        # consume "IN"
        # debugPrint(f"▶ DEBUG: matched IN keyword → `{tokens[new_index].value}`")
        # debugPrint(f"current condition: `{condition}`")
        condition += tokens[new_index].value
        new_index += 1

        # skip/preserve whitespace
        while new_index < len(tokens) and tokens[new_index].is_whitespace:
            condition += tokens[new_index].value
            new_index += 1

        # expect a parenthesis
        if (
            new_index < len(tokens)
            and isinstance(tokens[new_index], sqlparse.sql.Parenthesis)
        ):
            # find the IdentifierList inside the parentheses
            # (sqlparse nests comma-separated items there)
            ph        = get_field_column(schemas, token.value)   # single placeholder
            num_vals  = random.randint(2, 5)                     # 2-5 values
            in_list   = ", ".join([ph] * num_vals)

            condition += "(" + in_list + ")"
            return condition, new_index + 1

    # 3) BETWEEN a AND b — now supports bare or parenthesized operands
    if new_index < len(tokens) and tokens[new_index].value.strip().upper() == "BETWEEN":
        # consume "BETWEEN"
        condition += tokens[new_index].value
        new_index += 1

        # skip/preserve whitespace- can make skipping whitespace a func. no future changes tho, so maybe not needed
        while new_index < len(tokens) and tokens[new_index].is_whitespace:
            condition += tokens[new_index].value
            new_index += 1

        # helper to emit one operand (bare or inside parens)
        def _emit_operand():
            nonlocal new_index, condition
            ph = get_field_column(schemas, token.value)
            if (
                new_index < len(tokens)
                and isinstance(tokens[new_index], sqlparse.sql.Parenthesis)
            ):
                # drop the original parens, re-wrap our placeholder
                condition += f"({ph})"
                new_index += 1
            else:
                condition += ph
                new_index += 1

        # first operand
        _emit_operand()

        # skip/preserve whitespace
        while new_index < len(tokens) and tokens[new_index].is_whitespace:
            condition += tokens[new_index].value
            new_index += 1

        # consume "AND"
        if new_index < len(tokens) and tokens[new_index].value.strip().upper() == "AND":
            condition += tokens[new_index].value
            new_index += 1

        # second operand
        while new_index < len(tokens) and tokens[new_index].is_whitespace:
            condition += tokens[new_index].value
            new_index += 1
        _emit_operand()

        return condition, new_index

    # 4) fallback: no IN or BETWEEN
    return condition, new_index



def process_comparison_token(token, schemas):
    # printing the internal tokens of this comparison token
    #debugPrint("\ninside process_comparison_token")
    # for sub_token in token.tokens:
    #     debugPrint(f"▶ DEBUG: matched token → `{sub_token.value}`, type : {sub_token.ttype}")

    key, operator, value = re.split(
        r"((?:=|<|>|<=|>=|!=|LIKE)\s*)", token.value, maxsplit=1
    )
    #debugPrint(
    #    f"▶ DEBUG: split comparison token → key: `{key}`, operator: `{operator}`, value: `{value}`"
    #)
    if "_::INTERVAL" in value:
        field = re.sub(
            r"TIMESTAMP(TZ)?", "INTERVAL", get_field_column(schemas, key.strip())
        )
        new_val = value.replace("_::INTERVAL", f"{field}::INTERVAL")
        return f"{key}{operator.strip()}{new_val}"
    elif value.startswith("(") and value.endswith(")"):
        # key is something like "(col1, col2, col3)"
        # strip off the parens and split on commas to get the column names
        col_names = [c.strip() for c in key.strip()[1:-1].split(",")]

        # for each column, look up its placeholder via get_field_column(...)
        placeholders = ", ".join(get_field_column(schemas, col) for col in col_names)

        # re-assemble:   (col1, col2, col3) = (<ph1>, <ph2>, <ph3>)
        return f"{key}{operator.strip()}({placeholders})"
    else:
        new_val = re.sub(
            r"(?<![a-zA-Z0-9_])_(?![a-zA-Z0-9_])",
            get_field_column(schemas, key.strip()),
            value,
        )
        return f"{key}{operator}{new_val}"

'''
def process_parenthesis_token(token, parent_tokens, parent_index, schemas):
    debugPrint("\ninside process_parenthesis_token")
    for sub_token in token.tokens:
        debugPrint(
            f"▶ DEBUG: matched token → `{sub_token.value}`, type : {sub_token.ttype}"
        )
    if len(token.tokens) > 1 and isinstance(
        token.tokens[1], sqlparse.sql.IdentifierList
    ):
        condition = token.tokens[0].value  # Opening parenthesis
        sub_index = 1
        fields = [field.strip() for field in token.tokens[1].value.split(",")]
        condition += token.tokens[sub_index].value
        sub_index += 1
        condition += token.tokens[sub_index].value  # Add keyword after identifier list
        new_index = parent_index + 1
        while new_index < len(parent_tokens) and parent_tokens[new_index].is_whitespace:
            condition += " "
            new_index += 1
        if (
            new_index < len(parent_tokens)
            and parent_tokens[new_index].value.strip().upper() == "IN"
        ):
            condition += parent_tokens[new_index].value
            new_index += 1
        while new_index < len(parent_tokens) and parent_tokens[new_index].is_whitespace:
            condition += " "
            new_index += 1
        if new_index < len(parent_tokens) and isinstance(
            parent_tokens[new_index], sqlparse.sql.Parenthesis
        ):
            mapped_fields = ", ".join(
                f"({get_field_column(schemas, field)}, {get_field_column(schemas, field)})"
                for field in fields
            )
            condition += f"({mapped_fields})"
            return condition, new_index + 1
    else:
        index = 1
        inner_conditions = "("
        while index < len(token.tokens):
            cond, index = extract_where_condition(token.tokens, index, schemas)
            inner_conditions += cond
        return inner_conditions, parent_index + 1
'''

def process_parenthesis_token(token, parent_tokens, parent_index, schemas):
    """
    Handles multi-column IN-lists by zipping fields with each row of placeholders,
    and rewrites simple parenthesized WHERE conditions by re-invoking the WHERE parser.
    """
    # 1) Multi-column IN: "(a,b,...) IN ((...),(...),...)"
    if (
        len(token.tokens) > 1
        and isinstance(token.tokens[1], sqlparse.sql.IdentifierList)
    ):
        # LHS fields
        fields = [f.strip() for f in token.tokens[1].value.split(",")]

        # Build "(a,b)"
        condition = token.tokens[0].value  # "("
        condition += token.tokens[1].value  # "a,b"
        condition += token.tokens[2].value  # ")"
        new_index = parent_index + 1

        # Skip whitespace
        while new_index < len(parent_tokens) and parent_tokens[new_index].is_whitespace:
            condition += parent_tokens[new_index].value
            new_index += 1

        # Match "IN"
        if (
            new_index < len(parent_tokens)
            and parent_tokens[new_index].value.strip().upper() == "IN"
        ):
            debugPrint(f"▶ DEBUG: matched IN keyword → `{parent_tokens[new_index].value}`")
            condition += parent_tokens[new_index].value
            new_index += 1

        # Skip whitespace again
        while new_index < len(parent_tokens) and parent_tokens[new_index].is_whitespace:
            condition += parent_tokens[new_index].value
            new_index += 1

        # RHS: the Parenthesis holding the rows
        if (
            new_index < len(parent_tokens)
            and isinstance(parent_tokens[new_index], sqlparse.sql.Parenthesis)
        ):
            # --------- NEW: build 3-5 fresh tuples, ignore original rows -----
            num_rows   = random.randint(3, 5)           # ← change to 2-5 if you prefer
            tuple_ph   = "(" + ", ".join(
                            get_field_column(schemas, f) for f in fields
                         ) + ")"
            in_list    = ", ".join([tuple_ph] * num_rows)

            condition += "(" + in_list + ")"
            return condition, new_index + 1

    # 2) Fallback: simple "(cond)" — reparse and rewrite inner condition(s)
    inner = token.value[1:-1]  # drop the surrounding parentheses
    # parse the inner SQL fragment
    parsed = sqlparse.parse(inner)[0]
    rewritten = ""
    idx = 0
    subtoks = parsed.tokens
    while idx < len(subtoks):
        cond, idx = extract_where_condition(subtoks, idx, schemas)
        rewritten += cond
    # re-wrap in parentheses
    return f"({rewritten})", parent_index + 1

def extract_system_time(sql):
    system_time = get_system_time()

    # 1) Old pattern, e.g. “… OF SYSTEM TIME _ …”
    sql = re.sub(
        r"(\bOF\s+SYSTEM\s+TIME\s+)_",
        rf"\1'{system_time}'",
        sql,
        flags=re.IGNORECASE,
    )

    # 2) New Cockroach/Postgres syntax:
    #    “FOR SYSTEM_TIME AS OF _” → insert the timestamp in quotes
    sql = re.sub(
        r"(\bFOR\s+SYSTEM_TIME\s+AS\s+OF\s+)_",
        rf"\1'{system_time}'",
        sql,
        flags=re.IGNORECASE,
    )

    return sql


def get_system_time():
    minutes = random.randint(0, 59)
    seconds = random.randint(0, 59)
    return (
        dt.datetime.now(dt.timezone.utc)
        - dt.timedelta(minutes=minutes, seconds=seconds)
    ).strftime("%Y-%m-%d %H:%M:%S")


"""def extract_set_conditions(sql, schemas):
    def replace_set_clause(set_match):
        # The SET clause captured by group(3)
        set_str = set_match.group(3).strip()

        # Check if it is in the tuple form: (field1, field2) - (value1, value2)
        tuple_form = re.match(r"^\((.*?)\)\s*[-=]\s*\((.*?)\)$", set_str)
        if tuple_form:
            fields_str = tuple_form.group(1).strip()
            values_str = tuple_form.group(2).strip()

            fields = [f.strip() for f in fields_str.split(",")]
            values = [v.strip() for v in values_str.split(",")]
            set_clause = []
            for field, value in zip(fields, values):
                new_val = get_field_column(schemas, field)
                if value is not None:
                    # Replace the value with the dynamic value from schemas (or any processing)
                    new_val = re.sub(
                        r"(?<![a-zA-Z0-9_])_(?![a-zA-Z0-9_])", new_val, value
                    )
                set_clause.append(f"{field} = {new_val}")
            set_clause_str = ", ".join(set_clause)
        else:
            # Original "field=value" format (comma-separated)
            set_clause = []
            set_pairs = [pair.strip() for pair in set_str.split(",")]
            for set_pair in set_pairs:
                kv = [x.strip() for x in set_pair.split("=")]
                if len(kv) != 2:
                    continue  # or raise an error if appropriate
                field = kv[0]
                value = kv[1]
                new_val = get_field_column(schemas, field)
                if value is not None:
                    # Replace the value with the dynamic value from schemas (or any processing)
                    new_val = re.sub(
                        r"(?<![a-zA-Z0-9_])_(?![a-zA-Z0-9_])", new_val, value
                    )
                set_clause.append(f"{field} = {new_val}")
            set_clause_str = ", ".join(set_clause)

        return f"{set_match.group(1)}{set_match.group(2)}{set_clause_str}{set_match.group(4)}"

    # Match SET clause and stop at termination keywords (WHERE, ORDER BY, GROUP BY, LIMIT, etc.)
    return re.sub(
        r"(UPDATE\s+[\w.]+)(\s+SET\s+)(.+?)(\s+WHERE|\s+ORDER BY|\s+GROUP BY|\s+LIMIT|\s*;|$)",
        replace_set_clause,
        sql,
        flags=re.IGNORECASE,
    )"""


def extract_set_conditions(sql, schemas):
    def split_top_level_commas(s: str) -> list[str]:
        """
        Split on commas that are not inside any parentheses.
        E.g. "(1,2),3" → ["(1,2)", "3"]
        """
        parts = []
        buf = ""
        depth = 0
        for ch in s:
            if ch == "(":
                depth += 1
                buf += ch
            elif ch == ")":
                depth -= 1
                buf += ch
            elif ch == "," and depth == 0:
                parts.append(buf.strip())
                buf = ""
            else:
                buf += ch
        parts.append(buf.strip())
        return parts

    #new functionality for Case () when () then () ...when () type of sql statements
    def rewrite_case_expr(expr: str, target_col: str, schemas):
        # ── detect tuple-form  CASE (a,b) …  ──────────────────────────────
        tup = re.search(r'CASE\s*\(\s*([^)]+?)\s*\)', expr, flags=re.I)
        if tup:
            key_cols    = [c.strip() for c in tup.group(1).split(',')]
            tuple_mode  = True
        else:
            # scalar-key  CASE col …  (no parenthesis)
            scal = re.search(r'CASE\s+([a-zA-Z_][\w]*)', expr, flags=re.I)
            if not scal:                       # not a CASE we care about
                return expr
            key_cols    = [scal.group(1)]
            tuple_mode  = False

        key_ph  = [get_field_column(schemas, c) for c in key_cols]
        tgt_ph  = get_field_column(schemas, target_col)

        if tuple_mode:
            tuple_ph = '(' + ', '.join(key_ph) + ')'
            expr = re.sub(
                r'''WHEN\s*\(\s*(?:_|__more__)(?:\s*,\s*(?:_|__more__))*\s*\)
                    \s*THEN\s*(?:_|__more__)''',
                lambda _: f"WHEN {tuple_ph} THEN {tgt_ph}",
                expr, flags=re.I | re.X
            )
        else:  # scalar
            expr = re.sub(
                r'WHEN\s+_\s+THEN\s+_',  # WHEN _ THEN _
                f'WHEN {key_ph[0]} THEN {tgt_ph}',
                expr, flags=re.I
            )

        # ELSE force_error(_, _)
        expr = re.sub(
            r'force_error\s*\(\s*_\s*,\s*_\s*\)',
            f'force_error({", ".join(key_ph)})',
            expr, flags=re.I
        )
        return expr
    #case related functionality after returning clause
    def _rewrite_returning_clause(sql: str) -> str:
        """
        Locate  … RETURNING expr1, expr2, … [;]
        and rewrite every exprN exactly as we do in the SET-list:

            • CASE … THEN _      -> rewrite_case_expr(…)
            • stand-alone '_' / '__more__'
                                -> get_field_column(…)

        The helper _pick_target_column() chooses the right column to base the
        replacement on, while *ignoring* the anonymous placeholders “_” and
        “__more__” themselves (this was the piece that was missing before).
        """

        # ────────────────────────────────────────────────── helpers ──────────
        _sql_keywords = {
            "case", "when", "then", "else", "end",
            "left", "right", "upper", "lower", "substr",
        }
        _anon_markers = {"_", "__more__"}            

        def _pick_target_column(expr: str) -> str | None:
            """
            Scan `expr` from right-to-left and return the first identifier that:
            • is *not* a SQL keyword
            • is *not* one of the anonymous markers (“_”, “__more__”)
            • exists in `schemas`
            """
            for ident in reversed(re.findall(r"[a-zA-Z_][\w]*", expr)):
                ilow = ident.lower()
                if ilow in _sql_keywords or ident in _anon_markers:
                    continue
                try:
                    # raises KeyError if the column is unknown
                    get_field_column(schemas, ident)
                    return ident
                except KeyError:
                    continue
            return None
        # ─────────────────────────────────────────────────────────────────────

        m = re.search(r"\bRETURNING\b\s+(.+?)(;|$)", sql, flags=re.I | re.S)
        if not m:                                      # no RETURNING → leave as-is
            return sql

        prefix, expr_list, tail = sql[: m.start(1)], m.group(1), sql[m.end(1) :]
        parts  = split_top_level_commas(expr_list)     # your existing helper
        fixed  = []

        for p in parts:
            p   = p.strip()
            tgt = _pick_target_column(p)

            if tgt:
                if "CASE" in p.upper():                # rewrite CASE … THEN _
                    p = rewrite_case_expr(p, tgt, schemas)

                ph = get_field_column(schemas, tgt)    # placeholder for that column
                p  = re.sub(r"(?<!\w)_(?!\w)", ph, p)  # stand-alone “_”
                p  = p.replace("__more__", ph)         # “__more__”

            # If tgt is None we leave the expression untouched.
            fixed.append(p)

        return prefix + ", ".join(fixed) + tail




    def replace_set_clause(m):
        prefix = m.group(1)  # "UPDATE <table>"
        set_kw = m.group(2)  # " SET "
        body = m.group(3).strip()
        terminator = m.group(4)  # " WHERE …" or ";" or end
        #debugPrint(f"group divisions: prefix={prefix}, set_kw={set_kw}, body={body}, terminator={terminator}")

        # 1) Tuple-form: SET (a,b,...) = (v1,v2,...)
        tuple_match = re.match(r"^\((.*?)\)\s*=\s*\((.*)\)$", body)
        if tuple_match:
            fields_str = tuple_match.group(1)
            values_str = tuple_match.group(2)

            fields = split_top_level_commas(fields_str)
            values = split_top_level_commas(values_str)

            assignments = []
            for field, val in zip(fields, values):
                ph = get_field_column(schemas, field)
                # replace standalone "_" and "__more__" with the placeholder
                val = re.sub(r"(?<!\w)_(?!\w)", ph, val)
                val = val.replace("__more__", ph)
                assignments.append(f"{field} = {val}")

            new_body = ", ".join(assignments)

        else:

            # 2) Simple-form: SET a = v, b = v, ...
            pairs = split_top_level_commas(body)
            assignments = []
            for pair in pairs:
                if "=" not in pair:
                    continue
                field, val = pair.split("=", 1)
                field = field.strip()
                val = val.strip()

                if "CASE" in val.upper():
                    # strip prefix before CASE so rewrite_case_expr works on the pure CASE
                    before, case_part = re.split(r'(?i)\bCASE\b', val, 1)
                    rewritten = rewrite_case_expr('CASE' + case_part, field, schemas)
                    val = before + rewritten

                ph = get_field_column(schemas, field)
                val = re.sub(r"(?<!\w)_(?!\w)", ph, val)
                val = val.replace("__more__", ph)
                assignments.append(f"{field} = {val}")

            new_body = ", ".join(assignments)

        return f"{prefix}{set_kw}{new_body}{terminator}"
    
    pattern = re.compile(
        r"""
        (UPDATE\s+                                  # ①  whole “UPDATE …table” prefix
            (?:                                     #     ── quoted OR un-quoted identifier ──
                (?:"[^"]+"          |               #        "order"
                `[^`]+`          |               #        `order`
                \[[^\]]+\]       |               #        [order]
                [\w]+)                           #        order
                (?:\.
                    (?:"[^"]+"      |               #        "sales"."order"
                    `[^`]+`      |               #        `sales`.`order`
                    \[[^\]]+\]   |               #        [sales].[order]
                    [\w]+)                       #        sales.order
                )*                                  #        …and any extra dotted parts
            )
        )                                           # ①  ← keeps capturing everything above
        (\s+SET\s+)                                 # ②  literal “ SET ”
        (.+?)                                       # ③  SET-clause body
        (\s+WHERE|\s+ORDER\ BY|\s+GROUP\ BY|\s+LIMIT|\s*;|$)  # ④ terminator
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    sql = re.sub(pattern, replace_set_clause, sql)
    sql = _rewrite_returning_clause(sql)
    return sql


def get_field_column(schemas, field):
    # return f":-:'{field}':-:"
    for schema in schemas:
        if field in schema.columns:
            return str(schema.columns[field])
    raise ValueError(f"Field '{field}' not found in any schema")

#new function for cases where explicit values are not emntioned and need to extract info from data table itself
def get_field_table(all_schemas, table_name):
    """
    Build a single‐tuple placeholder for every column in `table_name`,
    based on the full schema mapping.
    """
    # Lookup the TableSchema by name
    ts = all_schemas[table_name]

    # For each column in the table, use its __str__ (or Column.__str__) to get the placeholder
    placeholders = [str(ts.columns[col_name]) for col_name in ts.columns.keys()]

    # Join into one parenthesized tuple
    return "(" + ", ".join(placeholders) + ")"


def extract_table_names(statement):
    # Regular expressions to match different SQL statements
    insert_pattern = re.compile(
        r'^INSERT INTO\s+["]?(?:[\w.]+\.)?(\w+)["]?', re.IGNORECASE
    )
    select_pattern = re.compile(
        r'^SELECT\s+.*?\s+FROM\s+["]?(?:[\w.]+\.)?(\w+)["]?', re.IGNORECASE
    )
    update_pattern = re.compile(r'^UPDATE\s+["]?(?:[\w.]+\.)?(\w+)["]?', re.IGNORECASE)
    delete_pattern = re.compile(
        r'^DELETE FROM\s+["]?(?:[\w.]+\.)?(\w+)["]?', re.IGNORECASE
    )
    join_pattern = re.compile(r'JOIN\s+["]?(?:[\w.]+\.)?(\w+)["]?', re.IGNORECASE)

    table_names = set()

    # Find all matches for each pattern
    table_names.update(insert_pattern.findall(statement))
    table_names.update(select_pattern.findall(statement))
    table_names.update(update_pattern.findall(statement))
    table_names.update(delete_pattern.findall(statement))
    table_names.update(join_pattern.findall(statement))

    return list(filter(None, table_names))


def debugPrint(msg):
    print(f"{msg}")
    pass
