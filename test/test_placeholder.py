#!/usr/bin/env python3
import re
import sys
from dbworkload.models.placeholder_processor import replace_placeholders
from dbworkload.models.ddl_generator import TableSchema, Column

OUTPUT_FILE = "test/test_output.txt"


def build_schemas():
    orders = TableSchema("bank.public.orders")
    for name, col_type, nullable, pk in [
        ("id", "UUID", True, True),
        ("acc_no", "INT", False, False),
        ("status", "STRING", False, False),
        ("amount", "DECIMAL(18,2)", True, False),
        ("updated_at", "TIMESTAMP", False, False),
    ]:
        orders.add_column(Column(name, col_type, nullable, pk))
    orders.set_primary_keys(["id"])

    ref = TableSchema("bank.public.ref_data")
    ref.add_column(Column("acc_no", "INT", False))
    ref.set_primary_keys([])

    return {"orders": orders, "ref_data": ref}


def main():
    schemas = build_schemas()
    examples = [
        # INSERT with/without cols
        "INSERT INTO orders VALUES (_,__more__);",
        "INSERT INTO orders(acc_no, status, amount) VALUES (_, __more__) RETURNING id;",
        "INSERT INTO orders(acc_no,status,amount) VALUES(_,__more__);",
        "INSERT INTO orders(acc_no, status, amount) VALUES  ( _ ,__more__ ) , (__, __more__) ;",
        "insert into orders(acc_no, status, amount) Values(_,__more__),( _,__more__ );",
        "INSERT INTO orders(acc_no, status, amount) VALUES (NOW(), _),(CURRENT_TIMESTAMP, __more__);",

        # EXTRA: three-row multi-tuple INSERT
        "INSERT INTO orders(acc_no, status, amount) VALUES (_,__more__),( _,__more__ ),(__more__, _);",

        # EXTRA: no-cols multi-tuple INSERT (3 rows)
        "INSERT INTO orders VALUES (_,__more__),( _,__more__),( __more__ , _);",

        # SELECT variants
        "SELECT id, IFNULL(sum(amount), _) FROM orders WHERE acc_no = _;",
        "SELECT IFNULL(status, _) AS name FROM orders;",
        "SELECT * FROM orders WHERE (acc_no = _) AND (id = _);",
        "SELECT * FROM orders WHERE id IN (_, __more__, _);",
        "SELECT * FROM orders WHERE (acc_no, status) IN ((_,__more__),( __more__ , _));",
        "SELECT * FROM orders FOR SYSTEM_TIME AS OF _ WHERE acc_no = _;",
        "SELECT * FROM ref_data WHERE acc_no = _;",
        "SELECT version();",
        " SELECT * FROM orders WHERE amount BETWEEN _ AND __more__;",

        # EXTRA: larger IN-lists
        "SELECT * FROM orders WHERE id IN (_, __more__, _, __more__, _);",
        "SELECT * FROM orders WHERE (acc_no, status) IN ((_,__more__),( __more__ , _),( _,__more__));",
        "SELECT * FROM orders WHERE amount BETWEEN (_ ) AND (__more__);",

        # UPDATE variants — simple form
        "UPDATE orders SET status = _ WHERE id = _;",
        "UPDATE orders SET status = _, amount = __more__ WHERE acc_no = _;",
        "UPDATE orders SET updated_at = NOW(), status = _ WHERE id = _;",

        # UPDATE variants — tuple form
        "UPDATE orders SET (acc_no, id) = (_, __more__) WHERE status = _;",
        "UPDATE orders SET (status, amount) = (__more__, _) WHERE id = _;",

        # DELETE
        "DELETE FROM orders WHERE acc_no = _;",
        "DELETE FROM orders WHERE (acc_no, id) = (_, __more__);",
    ]


    # 1) Clear the output file
    with open(OUTPUT_FILE, "w"):
        pass

    failures = 0
    for sql in examples:
        out = replace_placeholders(sql, schemas)

        # 2) Log IN/OUT
        separator = "-" * 60
        block = f"IN:  {sql}\nOUT: {out}\n{separator}\n"
        print(block, end="")
        with open(OUTPUT_FILE, "a") as f:
            f.write(block)

        # 3) Check for *actual* leftover raw placeholders:
        #    standalone '_' not part of an identifier
        if re.search(r"(?<!\w)_(?!\w)", out) or "__more__" in out:
            print(f"[ERROR] Placeholder left in output: {out}", file=sys.stderr)
            failures += 1

        # 4) For INSERTs *with* VALUES (any casing), verify tuple count
        if re.match(r"^\s*INSERT", sql, re.IGNORECASE) and re.search(
            r"\bVALUES\b", sql, re.IGNORECASE
        ):
            # case-insensitive split on VALUES
            in_parts = re.split(r"(?i)\bVALUES\b", sql, maxsplit=1)
            out_parts = re.split(r"(?i)\bVALUES\b", out, maxsplit=1)
            if len(in_parts) < 2 or len(out_parts) < 2:
                print(
                    f"[ERROR] Unexpected VALUES split failure on:\n  {sql}",
                    file=sys.stderr,
                )
                failures += 1
            else:
                in_part = in_parts[1]
                out_part = out_parts[1]

                tuples_in = len(re.split(r"\)\s*,\s*\(", in_part))
                tuples_out = len(re.findall(r"\([^()]*\)", out_part))

                if tuples_out != tuples_in:
                    print(
                        f"[ERROR] Tuple count mismatch: in={tuples_in}, out={tuples_out}\n  SQL: {sql}",
                        file=sys.stderr,
                    )
                    failures += 1

    if failures:
        print(f"\nFinished with {failures} failure(s).", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nAll tests passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
