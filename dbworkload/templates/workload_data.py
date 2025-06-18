# workload_data.py  – helper shared by stub.j2 runtime
#
# Usage inside the template:
#     from workload_data import generate_value_smart
#     ...
#     generate_value_smart('c_w_id', 'WHERE')

from collections import deque
import random
import yaml
from pathlib import Path
import re
from decimal import Decimal, ROUND_HALF_UP

# SimpleFaker stack
from dbworkload.utils.simplefaker_ca import SimpleFakerCA, _GEN_CLASS_MAP

# ---------------------------------------------------------------------------
# Thread-local singletons (module-level in Python = one copy per interpreter)
# ---------------------------------------------------------------------------
_generators:   dict[str, object] = {}            # col → iterator (INSERT / UPDATE)
_row_cache:    dict[str, deque]  = {}            # col → recent N values
_yaml_meta:    dict               = {}            # loaded YAML (lazy)
_parent_catalog: dict             = {}            # (canon_tbl, col) → (type, args)

EXEC_THREADS   = 1                               # assume original run used 1 procs
MAX_CACHE      = 10_000                          # ring-buffer per column

# ---------------------------------------------------------------------------
_DEC   = re.compile(r'\b(?:DECIMAL|NUMERIC)\b', re.I)
_P_S   = re.compile(r'\(\s*(\d+)\s*,\s*(\d+)\s*\)')

def _fix_dec(v, prec, scale):
    if v is None:
        return None
    d          = Decimal(str(v)).quantize(Decimal('1').scaleb(-scale), ROUND_HALF_UP)
    max_abs    = Decimal(10) ** (prec - scale-1)
    return d % max_abs if abs(d) >= max_abs else d

def gvs_from_bind(*args):
    col, sql_type, role = args[0], args[1], args[-1]
    val = generate_value_smart(col, role)

    if _DEC.search(sql_type):
        p, s = (12, 2)              # default if size missing
        m = _P_S.search(sql_type)
        if m:
            p, s = map(int, m.groups())
        val = _fix_dec(val, p, s)
    return val


def _canonical(name: str) -> str:
    """schema.table → schema__table (matches YAML keys)"""
    return name.replace(".", "__")

def _load_yaml() -> None:
    """Populate _yaml_meta & _parent_catalog once per thread."""
    global _yaml_meta, _parent_catalog
    if _yaml_meta:                       # already done
        return

    # --- locate the YAML ---------------------------------------------------
    # Keep it simple: look for tpcc.yaml in cwd or project root
    yml_path = next(
        (p for p in (Path.cwd(), Path.cwd().parent) if (p / "tpcc.yaml").exists()),
        None,
    )
    if yml_path is None:
        raise FileNotFoundError("tpcc.yaml not found in working dir or parent")
    with (yml_path / "tpcc.yaml").open("r", encoding="utf-8") as fh:
        _yaml_meta = yaml.safe_load(fh)

    # --- parent-catalog (needed for FKBlockWrapper) ------------------------
    for tbl, blocks in _yaml_meta.items():
        cols = blocks[0]["columns"]
        for col_name, col_meta in cols.items():
            # 3 canonical keys exactly like original generator
            for variant in (tbl,
                            f"public__{_canonical(tbl)}",
                            f"tpcc__public__{_canonical(tbl)}"):
                _parent_catalog[(variant, col_name)] = (
                    col_meta["type"],
                    col_meta["args"],
                    col_meta, 
                    blocks[0]["count"]
                )

# ---------------------------------------------------------------------------

def _build_generator(col_name: str):
    """
    Locate `col_name` in YAML, build a SimpleFaker iterator,
    preload it so that the first *count/EXEC_THREADS* values are
    consumed (they were already written to the CSV), seed the cache,
    and return the generator positioned at the *next* fresh value.
    """
    _load_yaml()

    # search every table for the column
    for tbl, blocks in _yaml_meta.items():
        block      = blocks[0]
        cols       = block["columns"]
        if col_name not in cols:
            continue

        col_meta   = cols[col_name]
        args       = dict(col_meta["args"])          # shallow copy
        args["_col_meta"] = col_meta                 # SimpleFaker hook
        count      = block["count"]                  # original row count

        faker = SimpleFakerCA()
        # inject parent-catalog so FKBlockWrapper works
        faker._parent_catalog = _parent_catalog

        gen_list   = faker.get_simplefaker_objects(
            col_meta["type"],
            args,
            count,
            EXEC_THREADS,
        )
        gen        = gen_list[0]                     # 1st thread’s slice

        # ---------- fast-forward & seed cache --------------------------------
        preload = count // EXEC_THREADS
        cache   = deque(maxlen=MAX_CACHE)
        for i in range(count):
            v = next(gen)
            if(i<preload):
                cache.append(v)

        _row_cache[col_name] = cache
        return gen

    # not found anywhere
    raise KeyError(f"Column {col_name!r} not present in YAML")

# ---------------------------------------------------------------------------

def generate_value_smart(col_name: str, role: str):
    """
    Main entry called from stub.j2.

    Parameters
    ----------
    col_name : str
        Column name as passed in the Jinja template.
    role     : str
        One of {"INSERT", "UPDATE", "WHERE"} – case-insensitive.
    """
    role = role.upper()

    # generator lookup / lazy build
    if col_name not in _generators:
        _generators[col_name] = _build_generator(col_name)
    gen   = _generators[col_name]
    cache = _row_cache[col_name]     # built alongside generator

    # Decide based on role
    if role in {"INSERT", "UPDATE"}:
        val = next(gen)
        cache.append(val)            # keep cache warm with new rows
        return val

    elif role == "WHERE":
        if cache:                    # prefer historic values
            return random.choice(cache)
        # fallback – cache empty (unlikely)
        return next(gen)

    else:
        raise ValueError(f"Unknown role {role!r} (expected INSERT / UPDATE / WHERE)")
