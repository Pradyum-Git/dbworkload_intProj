import builtins
import csv
import datetime as dt
import logging
import multiprocessing as mp
import os
import random
import uuid

import pandas as pd
import collections
import inspect
from copy import deepcopy          

from .common import import_class_at_runtime

logger = logging.getLogger("dbworkload")
USE_DB_DEFAULT = object()      # unique marker

def _support_seed(cls) -> bool:
    """Check if the class supports seeding."""
    sig = inspect.signature(cls.__init__)
    return "seed" in sig.parameters

# simplefaker_ca.py  – put it near DefaultWrapper / UniqueWrapper
class FKBlockWrapper:
    """Repeat each parent key `fanout` times for deterministic FK blocks."""
    def __init__(self,
                 parent_cls,            # generator *class* (not instance)
                 parent_args,           # dict without the 'seed'
                 parent_seed: float,
                 fanout: int           = 10,
                 needs_unique: bool    = False):
        # give every worker process a disjoint slice of the parent stream
        accepted = inspect.signature(parent_cls.__init__).parameters
        kwargs = {k: v for k, v in parent_args.items() if k in accepted}
        if _support_seed(parent_cls):
            kwargs["seed"] = parent_seed
        base_gen = parent_cls(**kwargs)
        if needs_unique:
            base_gen = UniqueWrapper(base_gen)

        self.parent_it = base_gen
        self.fanout    = max(1, fanout)
        self._counter  = 0
        self._current  = next(self.parent_it)

    def __iter__(self):
        return self

    def __next__(self):
        if self._counter == self.fanout:          # time to advance parent key
            self._current = next(self.parent_it)
            self._counter = 0
        self._counter += 1
        return self._current


class DefaultWrapper:
    """
    With probability `prob` returns the supplied `literal`;
    otherwise delegates to the wrapped generator.
    """
    def __init__(self, base_gen, prob: float, literal):
        self.base     = base_gen
        self.prob     = prob
        self.literal  = literal
        self.rng      = random.Random()

    def __iter__(self):
        return self

    def __next__(self):
        return self.literal if self.rng.random() < self.prob else next(self.base)


class UniqueWrapper:
    """
    Wraps a base generator and re-rolls until a value not seen in the
    recent window appears.  `cache_size` bounds RAM.
    """
    def __init__(self, base_gen, cache_size=100_000):
        self.base   = base_gen
        self.cache  = collections.deque(maxlen=cache_size)
        self.seen   = set()

    def __next__(self):
        while True:
            v = next(self.base)
            if v not in self.seen:            # first time we see it
                if len(self.cache) == self.cache.maxlen:
                    old = self.cache.popleft()
                    self.seen.remove(old)
                self.cache.append(v)
                self.seen.add(v)
                return v

    def __iter__(self):
        return self

class SimpleFakerCA:
    """Pseudo-random data generator based on
    the random.Random class.
    """

    def __init__(self, seed: float = None, csv_max_rows: int = 100000):
        self.csv_max_rows = csv_max_rows
        self.rng: random.Random = random.Random(seed)

    class Abc:
        def __init__(self, seed: float, null_pct: float = 0, array: int = 0):
            self.array = array
            self.null_pct = null_pct
            self.rng: random.Random = random.Random(seed)

    class Constant(Abc):
        """Iterator always yields the same value."""

        def __init__(self, value: str = "simplefaker", null_pct: float = 0):
            super().__init__(None, null_pct, 0)
            self.value = value

        def __next__(self):
            if self.rng.random() < self.null_pct:
                return ""
            return self.value

    class Sequence:
        """Iterator that counts upward forever."""

        def __init__(self, start: int = 0):
            self.start = start

        def __next__(self):
            start: int = self.start
            self.start += 1
            return start

    class UUIDv4(Abc):
        """Iterator thar yields a UUIDv4"""

        def __init__(self, seed: float = 0, null_pct: float = 0, array: int = 0):
            super().__init__(seed, null_pct, array)

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return uuid.UUID(int=self.rng.getrandbits(128), version=4)
                else:
                    return "{%s}" % ",".join(
                        [
                            str(uuid.UUID(int=self.rng.getrandbits(128), version=4))
                            for _ in range(self.array)
                        ]
                    )

    class Timestamp(Abc):
        """Iterator that yields a Timestamp string"""

        def __init__(
            self,
            start: str = "2000-01-01",
            end: str = "2024-12-31",
            format: str = "%Y-%m-%d %H:%M:%S.%f",
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(seed, null_pct, array)
            self.format = format
            self.start = int(dt.datetime.fromisoformat(start).timestamp()) * 1000000
            self.end = int(dt.datetime.fromisoformat(end).timestamp()) * 1000000

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return dt.datetime.fromtimestamp(
                        self.rng.randint(self.start, self.end) / 1000000
                    ).strftime(self.format)
                else:
                    return "{%s}" % ",".join(
                        [
                            dt.datetime.fromtimestamp(
                                self.rng.randint(self.start, self.end) / 1000000
                            ).strftime(self.format)
                            for _ in range(self.array)
                        ]
                    )

    class Date(Timestamp):
        """Iterator that yields a Date string"""

        def __init__(
            self,
            start: str = "2000-01-01",
            end: str = "2024-12-31",
            format: str = "%Y-%m-%d",
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(
                start=start,
                end=end,
                format=format,
                null_pct=null_pct,
                seed=seed,
                array=array,
            )

    class Time(Timestamp):
        """Iterator that yields a Time string"""

        def __init__(
            self,
            start: str = "07:30:00",
            end: str = "22:30:00",
            micros: bool = False,
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(
                start="1970-01-01 " + start,
                end="1970-01-01 " + end,
                format="%H:%M:%S" if not micros else "%H:%M:%S.%f",
                null_pct=null_pct,
                seed=seed,
                array=array,
            )

    class String(Abc):
        """Iterator that yields a truly random string of ascii characters"""

        def __init__(
            self,
            min: int = 10,
            max: int = 50,
            prefix: str = "",
            seed: float = 0.0,
            null_pct: float = 0.0,
            array: int = 0,
        ):
            super().__init__(seed, null_pct, array)
            self.min = min
            self.max = max
            self.prefix = prefix

            assert min >= 0
            assert min <= max

            # make translation table from 0..255 to 97..122
            self.tbl = bytes.maketrans(
                bytearray(range(256)),
                bytearray(
                    [ord(b"a") + b % 26 for b in range(113)]
                    + [ord(b"0") + b % 10 for b in range(30)]
                    + [ord(b"A") + b % 26 for b in range(113)]
                ),
            )

        # generate random bytes and translate them to ascii
        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                size = self.rng.randint(self.min, self.max)
                if not self.array:
                    return (
                        self.prefix
                        + self.rng.getrandbits(8 * size)
                        .to_bytes(size, "big")
                        .translate(self.tbl)
                        .decode()
                    )
                else:
                    return "{%s}" % ",".join(
                        f"{self.prefix}{x}"
                        for x in [
                            self.rng.getrandbits(size * 8)
                            .to_bytes(size, "big")
                            .translate(self.tbl)
                            .decode()
                            for _ in range(self.array)
                        ]
                    )

    class Json(String):
        """Iterator that yields a simple json string"""

        def __init__(
            self,
            min: int = 10,
            max: int = 50,
            seed: float = 0,
            null_pct: float = 0,
        ):
            # 9 is the number of characters in the hardcoded string
            self.min = builtins.max(min - 9, 1)
            self.max = builtins.max(max - 9, 2)
            super().__init__(
                min=self.min, max=self.max, null_pct=null_pct, seed=seed, array=0
            )

        def __next__(self):
            v = super().__next__()
            if not v:
                return ""
            return '{"k":"%s"}' % v

    class Integer(Abc):
        """Iterator that yields a random integer"""

        def __init__(
            self,
            min: int = 1,
            max: int = 1000000000,
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(seed, null_pct, array)
            self.min_num = min
            self.max_num = max

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return self.rng.randint(self.min_num, self.max_num)
                else:
                    return "{%s}" % ",".join(
                        [
                            str(self.rng.randint(self.min_num, self.max_num))
                            for _ in range(self.array)
                        ]
                    )

    class Bit(Abc):
        """Iterator that yields random bits"""

        def __init__(
            self,
            size: int = 10,
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(seed, null_pct, array)
            self.size = size

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return "".join(
                        [str(int(self.rng.random() > 0.5)) for _ in range(self.size)]
                    )
                else:
                    return "{%s}" % ",".join(
                        [
                            "".join(
                                [
                                    str(int(self.rng.random() > 0.5))
                                    for _ in range(self.size)
                                ]
                            )
                            for _ in range(self.array)
                        ]
                    )

    class Bool(Abc):
        """Iterator that yields a random boolean (0, 1)"""

        def __init__(self, seed: float, null_pct: float = 0, array: int = 0):
            super().__init__(seed, null_pct, array)

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return int(self.rng.random() > 0.5)
                else:
                    return "{%s}" % ",".join(
                        [str(int(self.rng.random() > 0.5)) for _ in range(self.array)]
                    )

    class Float(Abc):
        """Iterator that yields a random float number"""

        def __init__(
            self,
            min: int = 0,
            max: int = 1000000,
            round: int = 2,
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(seed, null_pct, array)
            self.min = min
            self.max = max - 1  # max value must not be inclusive
            self.round = round

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return round(self.rng.uniform(self.min, self.max), self.round)
                else:
                    return "{%s}" % ",".join(
                        [
                            str(round(self.rng.uniform(self.min, self.max), self.round))
                            for _ in range(self.array)
                        ]
                    )

    class Bytes(Abc):
        """Iterator that yields a random byte array"""

        def __init__(
            self,
            size: int = 20,
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            self.size = size
            super().__init__(seed, null_pct, array)

            # make translation table from 0..255 to hex chars 'abcdef0123456789'
            self.hex_tbl = bytes.maketrans(
                bytearray(range(256)),
                bytearray(
                    [ord(b"a") + b % 6 for b in range(160)]
                    + [ord(b"0") + b % 10 for b in range(96)]
                ),
            )

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return "\\x" + (
                        self.rng.getrandbits(8 * self.size)
                        .to_bytes(self.size, "big")
                        .translate(self.hex_tbl)
                        .decode()
                    )

                else:
                    return "{%s}" % ",".join(
                        f'"\\\\x{x}"'
                        for x in [
                            self.rng.getrandbits(self.size * 8)
                            .to_bytes(self.size, "big")
                            .translate(self.hex_tbl)
                            .decode()
                            for _ in range(self.array)
                        ]
                    )

    class Choice(Abc):
        """Iterator that yields 1 item from a list"""

        def __init__(
            self,
            population: list = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            weights: list = None,
            cum_weights: list = None,
            seed: float = 0,
            null_pct: float = 0,
            array: int = 0,
        ):
            super().__init__(seed, null_pct, array)
            self.population = population
            self.weights = weights
            self.cum_weights = cum_weights

        def __next__(self):
            if self.null_pct and self.rng.random() < self.null_pct:
                return ""
            else:
                if not self.array:
                    return self.rng.choices(
                        self.population,
                        weights=self.weights,
                        cum_weights=self.cum_weights,
                    )[0]
                else:
                    return "{%s}" % ",".join(
                        [
                            self.rng.choices(
                                self.population,
                                weights=self.weights,
                                cum_weights=self.cum_weights,
                            )[0]
                            for _ in range(self.array)
                        ]
                    )

    def division_with_modulo(self, total: int, divider: int):
        """Split a number into chunks.
        Eg: total=10, divider=3 returns [3,3,4]

        Args:
            total (int): The number to divide
            divider (int): the count of chunks

        Returns:
            (list): the list of the individual chunks
        """
        rows_to_process = int(total / divider)
        rows_left_over = total % divider

        if rows_left_over == 0:
            return [rows_to_process] * divider
        else:
            l = [rows_to_process] * (divider - 1)
            l.append(rows_to_process + rows_left_over)
            return l

    """
    the seed in the yaml file `1` is used to create a rng used to 
    generate the seed number for each SimpleFaker class
    
    >>> rng = random.Random(1)
    >>> seed1 = rng.random()
    >>> seed2 = rng.random()
    >>> 
    >>> 
    >>> rng1 = random.Random(seed1)
    >>> rng1.randint(0, 1000000)
    948735
    >>> rng1.randint(0, 1000000)
    614390
    >>> 
    >>> rng2 = random.Random(seed2)
    >>> rng2.randint(0, 1000000)
    140545
    >>> rng2.randint(0, 1000000)
    157597
    """

    def generate(
        self,
        load: dict,
        exec_threads: int,
        csv_dir: str,
        delimiter: str,
        compression: str,
    ):
        """Generate the CSV datasets

        Args:
            load (dict): the data generation definition
            exec_threads (int): count of processes for parallel execution
            csv_dir (str): destination directory for the CSV files
            delimiter (str): field delimiter
            compression (str): the compression format (gzip, zip, None..)
        """
        # --- parent-column catalog: {(canon_table, col) : (gen_type, gen_args)} ----
        debugPrint("generate called")
        parent_catalog = {}
        for tbl, blocks in load.items():
            cols = blocks[0]["columns"]
            for col_name, col_meta in cols.items():
                two_level_table = f"public__{tbl}"
                three_level_table = f"tpcc__{two_level_table}"
                parent_catalog[(tbl, col_name)] = (col_meta["type"],
                                                col_meta["args"])
                parent_catalog[(two_level_table, col_name)] = (col_meta["type"],
                                                col_meta["args"])
                parent_catalog[(three_level_table, col_name)] = (col_meta["type"],
                                                col_meta["args"])
                debugPrint(f"added ({col_meta["type"]},{col_meta["args"]}) to parent catalog with keys : ({tbl},{col_name}),({two_level_table},{col_name}),({three_level_table},{col_name})")

        self._parent_catalog = parent_catalog

        for canon_tbl, blocks in load.items():
            cols   = blocks[0]["columns"]

        for table_name, table_details in load.items():
            csv_file_basename = os.path.join(csv_dir, table_name)

            logger.info(f"Generating dataset for table '{table_name}'")

            for item in table_details:
                col_names = list(item["columns"].keys())
                sort_by = item.get("sort-by", [])

                for col, col_details in item["columns"].items():
                    args = col_details.get("args", {})
                    args["_col_meta"] = col_details
                    # get the list of simplefaker objects with different seeds
                    item["columns"][col] = self.get_simplefaker_objects(
                        col_details["type"],
                        args,
                        item["count"],
                        exec_threads,
                    )

                # create a zip object so that generators are paired together
                z = zip(*[x for x in item["columns"].values()])

                rows_chunk = self.division_with_modulo(item["count"], exec_threads)
                procs = []
                for i, rows in enumerate(rows_chunk):
                    output_file = (
                        csv_file_basename
                        + "."
                        + str(table_details.index(item))
                        + "_"
                        + str(i)
                    )

                    p = mp.Process(
                        target=self.worker,
                        daemon=True,
                        args=(
                            next(z),
                            rows,
                            output_file,
                            col_names,
                            sort_by,
                            delimiter,
                            compression,
                        ),
                    )
                    p.start()
                    procs.append(p)

                # wait for all workers to exit
                for p in procs:
                    p.join()

    def get_simplefaker_objects(self, obj_type: str, args: dict, count: int, exec_threads: int):
        col_meta = args.pop("_col_meta", {})       # ← injected earlier
        r = random.Random(args.pop("seed", None))
        seeds = [r.random() for _ in range(exec_threads)]

        obj_type = obj_type.lower()

        # ─── Build the *base* generator list ───────────────────────────────
        if obj_type == "constant":
            base_gens = [SimpleFakerCA.Constant(**args) for _ in range(exec_threads)]
        elif obj_type == "sequence":
            div   = count // exec_threads
            start = int(args.get("start", 0))
            base_gens = [SimpleFakerCA.Sequence(div * x + start) for x in range(exec_threads)]
        elif obj_type == "integer":
            base_gens = [SimpleFakerCA.Integer(seed=s, **args) for s in seeds]
        elif obj_type == "float":
            base_gens = [SimpleFakerCA.Float(seed=s, **args) for s in seeds]
        elif obj_type == "string":
            base_gens = [SimpleFakerCA.String(seed=s, **args) for s in seeds]
        elif obj_type == "json":
            base_gens = [SimpleFakerCA.Json(seed=s, **args) for s in seeds]
        elif obj_type == "choice":
            base_gens = [SimpleFakerCA.Choice(seed=s, **args) for s in seeds]
        elif obj_type == "timestamp":
            base_gens = [SimpleFakerCA.Timestamp(seed=s, **args) for s in seeds]
        elif obj_type == "time":
            base_gens = [SimpleFakerCA.Time(seed=s, **args) for s in seeds]
        elif obj_type == "date":
            base_gens = [SimpleFakerCA.Date(seed=s, **args) for s in seeds]
        elif obj_type == "uuid":
            base_gens = [SimpleFakerCA.UUIDv4(seed=s, **args) for s in seeds]
        elif obj_type == "bool":
            base_gens = [SimpleFakerCA.Bool(seed=s, **args) for s in seeds]
        elif obj_type == "bit":
            base_gens = [SimpleFakerCA.Bit(seed=s, **args) for s in seeds]
        elif obj_type == "bytes":
            base_gens = [SimpleFakerCA.Bytes(seed=s, **args) for s in seeds]
        elif obj_type == "custom":
            custom_gen = import_class_at_runtime(args.pop("path"))
            base_gens = [custom_gen(seed=s, **args) for s in seeds]
        else:
            raise ValueError(f"SimpleFaker type not implemented: '{obj_type}'")

        # ─── Apply UniqueWrapper if needed ─────────────────────────────────
        need_unique = (
            # 1. Column declared UNIQUE, but *not* an FK (child-side may repeat)
            col_meta.get("isUnique") and not col_meta.get("hasForeignKey")
            # 2. …or column is part of the PRIMARY KEY
            or col_meta.get("isPrimaryKey")
        ) and obj_type not in {"sequence", "uuid"}   # those emit unique values already
        if need_unique:
            base_gens = [UniqueWrapper(g) for g in base_gens]

        # ─── DefaultWrapper (simple literals) ───────────────────────────────
        if "default_prob" in col_meta and "default" in col_meta:
            p   = float(col_meta["default_prob"])
            lit = col_meta["default"]
            if 0.0 < p <= 1.0:
                base_gens = [DefaultWrapper(g, p, lit) for g in base_gens]

        # --- FK wrapper ----------------------------------------------------
        if col_meta.get("hasForeignKey") :
            canon_parent, parent_col = col_meta["fk"].split(".")
            p_type, p_args = self._parent_catalog[(canon_parent, parent_col)]

            parent_cls = _GEN_CLASS_MAP[p_type]
            p_args     = {k: v for k, v in p_args.items() if k != "seed"}

            fan        = int(col_meta.get("fanout", 10))
            yaml_seed  = col_meta["parent_seed"]
            needs_unique_parent = parent_cls not in (
                SimpleFakerCA.UUIDv4,
                SimpleFakerCA.Sequence,
            )

            # === reproduce *parent* per-thread seeds exactly ===
            rng_for_parent = random.Random(yaml_seed)
            parent_thread_seeds = [rng_for_parent.random() for _ in range(exec_threads)]

            base_gens = [
                FKBlockWrapper(
                    parent_cls,
                    p_args,
                    parent_thread_seeds[i],     # << same seed the parent used
                    fanout=fan,
                    needs_unique=needs_unique_parent,
                )
                for i in range(exec_threads)
            ]


        return base_gens

    def worker(
        self,
        generators: tuple,
        iterations: int,
        basename: str,
        col_names: list,
        sort_by: list,
        separator: str,
        compression: str,
    ):
        """Process worker function to generate the data in a multiprocessing env

        Args:
            generators (tuple): the SimpleFaker data gen objects
            iterations (int): count of rows to generate
            basename (str): the basename of the output csv file
            col_names (list): the csv column names, used for sorting
            sort_by (list): the column to sort by
            separator (str): the field delimiter in the CSV file
            compression (str): the compression format (gzip, zip, None..)
        """

        def gen_to_csv(iters: int):
            # create individual Series and then concat them together
            df = pd.concat(
                [pd.Series([next(gen) for _ in range(iters)]) for gen in generators],
                axis=1,
                keys=col_names,
            )

            # get a list of the colums that are not to be sorted by
            remaining = list(set(col_names) - set(sort_by))

            # create a dataframe by concatenating:
            # 1 - the df subset with the sort_by columns sorted by the sort_by columns
            # 2 - the df subset with the remaining columns
            # finally order the columns by the original col_names
            # then save to csv
            pd.concat(
                [
                    df[sort_by].sort_values(sort_by).reset_index(drop=True),
                    df[remaining],
                ],
                axis=1,
            )[col_names].to_csv(
                basename + "_" + str(counter) + suffix,
                quoting=csv.QUOTE_MINIMAL,
                sep=separator,
                header=False,
                index=False,
                compression=compression,
            )

        logger.debug("SimpleFaker worker created")
        if iterations > self.csv_max_rows:
            count = iterations // self.csv_max_rows
            rem = iterations % self.csv_max_rows
            iterations = self.csv_max_rows
        else:
            count = 1
            rem = 0

        suffix = ".tsv" if separator == "\t" else ".csv"

        if compression:
            suffix += "." + {
                "gzip": "gz",
            }.get(compression, compression)

        for counter in range(count):
            try:
                gen_to_csv(iterations)
            except csv.Error as e:
                logger.error(e)
                if e.args[0] == "need to escape, but no escapechar set":
                    logger.error(
                        f"You cannot use the selected delimiter '{separator}'. Consider using another char or the the tab key."
                    )

            logger.debug(f"Saved file '{basename + '_' + str(counter) + suffix}'")

        # remaining rows, if any
        if rem > 0:
            counter = count
            gen_to_csv(rem)

            logger.debug(f"Saved file '{basename + '_' + str(counter) + suffix}'")

# --- after the whole class ----------------------
_GEN_CLASS_MAP = {
    "constant":  SimpleFakerCA.Constant,
    "sequence":  SimpleFakerCA.Sequence,
    "uuid":      SimpleFakerCA.UUIDv4,
    "integer":   SimpleFakerCA.Integer,
    "float":     SimpleFakerCA.Float,
    "string":    SimpleFakerCA.String,
    "json":      SimpleFakerCA.Json,
    "timestamp": SimpleFakerCA.Timestamp,
    "time":      SimpleFakerCA.Time,
    "date":      SimpleFakerCA.Date,
    "bool":      SimpleFakerCA.Bool,
    "bit":       SimpleFakerCA.Bit,
    "bytes":     SimpleFakerCA.Bytes,
}

# Open the debug output file outside the function
debug_outfile = open("faker_output.txt", "a")

def debugPrint(msg: str):
    print(f"[DEBUG] {msg}", file=debug_outfile, flush=True)