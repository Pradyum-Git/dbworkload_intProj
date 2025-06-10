# tests/test_ddl_to_yaml.py
# ------------------------------------------------------------
# Verify that the new ddl_to_yaml_ca() turns a set of real
# CREATE TABLE statements into the richer YAML spec.
#
# ❶  parse_ddl  ──► TableSchema objects
# ❷  collate into dict[str, TableSchema]
# ❸  ddl_to_yaml_ca("", schemas) ──► YAML string
# ❹  emit to test_yaml_output.txt
# ------------------------------------------------------------
from pathlib import Path
from datetime import datetime

from dbworkload.models.ddl_generator import parse_ddl          # your parser
from dbworkload.utils.common import ddl_to_yaml_ca     # new function

{
# # ---------------- DDL examples (same as your earlier test) ----
# EXAMPLES = [
#     # 1 ─── Lookup table (single-column PK, UNIQUE text)
#     """CREATE TABLE IF NOT EXISTS public.countries (
#         code CHAR(2)  PRIMARY KEY,
#         name TEXT NOT NULL UNIQUE
#     )""",

#     # 2 ─── Users (serial PK, FK to countries, literal DEFAULT, UNIQUE email)
#     """CREATE TABLE IF NOT EXISTS public.users (
#         id SERIAL PRIMARY KEY,
#         country_code CHAR(2) NOT NULL REFERENCES countries(code),
#         email TEXT UNIQUE,
#         signup_at TIMESTAMPTZ NOT NULL DEFAULT now()
#     )""",

#     # 3 ─── Products (varchar PK, price CHECK, composite UNIQUE)
#     """CREATE TABLE IF NOT EXISTS public.products (
#         sku VARCHAR(20) NOT NULL,
#         name TEXT NOT NULL,
#         price DECIMAL(10,4) NOT NULL CHECK (price > 0),
#         category TEXT NOT NULL,
#         CONSTRAINT products_pk PRIMARY KEY (sku),
#         UNIQUE (name, category)
#     )""",

#     # 4 ─── Orders (UUID PK with function DEFAULT, FK → users)
#     """CREATE TABLE IF NOT EXISTS public.orders (
#         id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#         user_id INT NOT NULL REFERENCES users(id),
#         order_total DECIMAL(12,2) DEFAULT 0
#     )""",

#     # 5 ─── Order-items (composite PK, two FKs, integer DEFAULT)
#     """CREATE TABLE IF NOT EXISTS public.order_items (
#         order_id UUID NOT NULL REFERENCES orders(id),
#         line_no INT  NOT NULL,
#         product_sku VARCHAR(20) NOT NULL REFERENCES products(sku),
#         qty INT NOT NULL DEFAULT 1,
#         PRIMARY KEY (order_id, line_no)
#     )""",

#     # 6 ─── Flags (PK text, bool DEFAULT, bit column, CHECK)
#     """CREATE TABLE IF NOT EXISTS public.flags (
#         flag_name TEXT PRIMARY KEY,
#         is_active BOOL NOT NULL DEFAULT true,
#         flags_mask BIT(8) NOT NULL,
#         CHECK ((B'1' = flags_mask & B'1'))
#     )""",

#     # 7 ─── Tags (UUID PK + TEXT[] DEFAULT)
#     """CREATE TABLE IF NOT EXISTS public.tags (
#         id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#         name TEXT NOT NULL,
#         aliases TEXT[] DEFAULT ARRAY[]::TEXT[]
#     )""",

#     # 8 ─── Measurements (composite PK, FK to ref_data, JSON column)
#     """CREATE TABLE IF NOT EXISTS public.measurements (
#         acc_no INT8 NOT NULL REFERENCES public.ref_data(acc_no),
#         id UUID    NOT NULL,
#         measured_value FLOAT8,
#         valid BOOL DEFAULT false,
#         measured_data JSON NOT NULL DEFAULT '{}'::JSON,
#         PRIMARY KEY (acc_no, id),
#         CONSTRAINT fk_test FOREIGN KEY (acc_no, id) REFERENCES public.order_items(order_id, line_no)
#     )""",

#     # 9 ─── Audit log (function DEFAULTs, FK, no PK to test INSERT w/o PK)
#     """CREATE TABLE IF NOT EXISTS audit.log_entries (
#         entry_id UUID DEFAULT uuid_generate_v4(),
#         order_id UUID REFERENCES public.orders(id),
#         action TEXT NOT NULL,
#         ts TIMESTAMPTZ DEFAULT now()
#     )""",

#     # 10 ─── Quoted identifiers, composite UNIQUE, ARRAY FK demo
#     '''CREATE TABLE IF NOT EXISTS "MySchema"."Quoted-Table" (
#         "Id-Num"   INT  PRIMARY KEY,
#         "Codes"    TEXT[] NOT NULL,
#         "RefTags"  UUID[] REFERENCES public.tags(id),
#         CONSTRAINT uq_codes UNIQUE("Codes")
#     )''',

#     #-- 11 ─── Shipments (single-column FK + composite FK)
#     '''CREATE TABLE IF NOT EXISTS logistics.shipments (
#         shipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#         order_id    UUID NOT NULL,
#         line_no     INT  NOT NULL,
#         product_sku VARCHAR(20) NOT NULL,
#         shipped_at  TIMESTAMPTZ DEFAULT now(),
#         CONSTRAINT fk_prod FOREIGN KEY (product_sku) REFERENCES public.products(sku),
#         CONSTRAINT fk_order_item FOREIGN KEY (order_id, line_no) REFERENCES public.order_items(order_id, line_no)
#     )'''
# ]
}

EXAMPLES = [
    # warehouse table
    """CREATE TABLE public.warehouse (
        w_id INT8 NOT NULL,
        w_name VARCHAR(10) NOT NULL,
        w_street_1 VARCHAR(20) NOT NULL,
        w_street_2 VARCHAR(20) NOT NULL,
        w_city VARCHAR(20) NOT NULL,
        w_state CHAR(2) NOT NULL,
        w_zip CHAR(9) NOT NULL,
        w_tax DECIMAL(4,4) NOT NULL,
        w_ytd DECIMAL(12,2) NOT NULL,
        CONSTRAINT warehouse_pkey PRIMARY KEY (w_id ASC)
    )""",

    # district table
    """CREATE TABLE public.district (
        d_id INT8 NOT NULL,
        d_w_id INT8 NOT NULL,
        d_name VARCHAR(10) NOT NULL,
        d_street_1 VARCHAR(20) NOT NULL,
        d_street_2 VARCHAR(20) NOT NULL,
        d_city VARCHAR(20) NOT NULL,
        d_state CHAR(2) NOT NULL,
        d_zip CHAR(9) NOT NULL,
        d_tax DECIMAL(4,4) NOT NULL,
        d_ytd DECIMAL(12,2) NOT NULL,
        d_next_o_id INT8 NOT NULL,
        CONSTRAINT district_pkey PRIMARY KEY (d_w_id ASC, d_id ASC),
        CONSTRAINT district_d_w_id_fkey FOREIGN KEY (d_w_id) REFERENCES public.warehouse(w_id) NOT VALID
    )""",

    # customer table
    """CREATE TABLE public.customer (
        c_id INT8 NOT NULL,
        c_d_id INT8 NOT NULL,
        c_w_id INT8 NOT NULL,
        c_first VARCHAR(16) NOT NULL,
        c_middle CHAR(2) NOT NULL,
        c_last VARCHAR(16) NOT NULL,
        c_street_1 VARCHAR(20) NOT NULL,
        c_street_2 VARCHAR(20) NOT NULL,
        c_city VARCHAR(20) NOT NULL,
        c_state CHAR(2) NOT NULL,
        c_zip CHAR(9) NOT NULL,
        c_phone CHAR(16) NOT NULL,
        c_since TIMESTAMP NOT NULL,
        c_credit CHAR(2) NOT NULL,
        c_credit_lim DECIMAL(12,2) NOT NULL,
        c_discount DECIMAL(4,4) NOT NULL,
        c_balance DECIMAL(12,2) NOT NULL,
        c_ytd_payment DECIMAL(12,2) NOT NULL,
        c_payment_cnt INT8 NOT NULL,
        c_delivery_cnt INT8 NOT NULL,
        c_data VARCHAR(500) NOT NULL,
        CONSTRAINT customer_pkey PRIMARY KEY (c_w_id ASC, c_d_id ASC, c_id ASC),
        CONSTRAINT customer_c_w_id_c_d_id_fkey FOREIGN KEY (c_w_id, c_d_id)
            REFERENCES public.district(d_w_id, d_id) NOT VALID,
        INDEX customer_idx (c_w_id ASC, c_d_id ASC, c_last ASC, c_first ASC)
    )""",

    # history table
    """CREATE TABLE public.history (
        rowid UUID NOT NULL DEFAULT gen_random_uuid(),
        h_c_id INT8 NOT NULL,
        h_c_d_id INT8 NOT NULL,
        h_c_w_id INT8 NOT NULL,
        h_d_id INT8 NOT NULL,
        h_w_id INT8 NOT NULL,
        h_date TIMESTAMP NULL,
        h_amount DECIMAL(6,2) NULL,
        h_data VARCHAR(24) NULL,
        CONSTRAINT history_pkey PRIMARY KEY (h_w_id ASC, rowid ASC),
        CONSTRAINT history_h_c_w_id_h_c_d_id_h_c_id_fkey FOREIGN KEY (h_c_w_id, h_c_d_id, h_c_id)
            REFERENCES public.customer(c_w_id, c_d_id, c_id) NOT VALID,
        CONSTRAINT history_h_w_id_h_d_id_fkey FOREIGN KEY (h_w_id, h_d_id)
            REFERENCES public.district(d_w_id, d_id) NOT VALID
    )""",

    # "order" table (quoted identifier)
    """CREATE TABLE public."order" (
        o_id INT8 NOT NULL,
        o_d_id INT8 NOT NULL,
        o_w_id INT8 NOT NULL,
        o_c_id INT8 NULL,
        o_entry_d TIMESTAMP NULL,
        o_carrier_id INT8 NULL,
        o_ol_cnt INT8 NULL,
        o_all_local INT8 NULL,
        CONSTRAINT order_pkey PRIMARY KEY (o_w_id ASC, o_d_id ASC, o_id DESC),
        CONSTRAINT order_o_w_id_o_d_id_o_c_id_fkey FOREIGN KEY (o_w_id, o_d_id, o_c_id)
            REFERENCES public.customer(c_w_id, c_d_id, c_id) NOT VALID,
        UNIQUE INDEX order_idx (o_w_id ASC, o_d_id ASC, o_c_id ASC, o_id DESC)
            STORING (o_entry_d, o_carrier_id)
    )""",

    # new_order table
    """CREATE TABLE public.new_order (
        no_o_id INT8 NOT NULL,
        no_d_id INT8 NOT NULL,
        no_w_id INT8 NOT NULL,
        CONSTRAINT new_order_pkey PRIMARY KEY (no_w_id ASC, no_d_id ASC, no_o_id ASC),
        CONSTRAINT new_order_no_w_id_no_d_id_no_o_id_fkey FOREIGN KEY (no_w_id, no_d_id, no_o_id)
            REFERENCES public."order"(o_w_id, o_d_id, o_id) NOT VALID
    )""",

    # item table
    """CREATE TABLE public.item (
        i_id INT8 NOT NULL,
        i_im_id INT8 NULL,
        i_name VARCHAR(24) NULL,
        i_price DECIMAL(5,2) NULL,
        i_data VARCHAR(50) NULL,
        CONSTRAINT item_pkey PRIMARY KEY (i_id ASC)
    )""",

    # stock table
    """CREATE TABLE public.stock (
        s_i_id INT8 NOT NULL,
        s_w_id INT8 NOT NULL,
        s_quantity INT8 NULL,
        s_dist_01 CHAR(24) NULL,
        s_dist_02 CHAR(24) NULL,
        s_dist_03 CHAR(24) NULL,
        s_dist_04 CHAR(24) NULL,
        s_dist_05 CHAR(24) NULL,
        s_dist_06 CHAR(24) NULL,
        s_dist_07 CHAR(24) NULL,
        s_dist_08 CHAR(24) NULL,
        s_dist_09 CHAR(24) NULL,
        s_dist_10 CHAR(24) NULL,
        s_ytd INT8 NULL,
        s_order_cnt INT8 NULL,
        s_remote_cnt INT8 NULL,
        s_data VARCHAR(50) NULL,
        CONSTRAINT stock_pkey PRIMARY KEY (s_w_id ASC, s_i_id ASC),
        CONSTRAINT stock_s_w_id_fkey FOREIGN KEY (s_w_id) REFERENCES public.warehouse(w_id) NOT VALID,
        CONSTRAINT stock_s_i_id_fkey FOREIGN KEY (s_i_id) REFERENCES public.item(i_id) NOT VALID
    )""",

    # order_line table
    """CREATE TABLE public.order_line (
        ol_o_id INT8 NOT NULL,
        ol_d_id INT8 NOT NULL,
        ol_w_id INT8 NOT NULL,
        ol_number INT8 NOT NULL,
        ol_i_id INT8 NOT NULL,
        ol_supply_w_id INT8 NULL,
        ol_delivery_d TIMESTAMP NULL,
        ol_quantity INT8 NULL,
        ol_amount DECIMAL(6,2) NULL,
        ol_dist_info CHAR(24) NULL,
        CONSTRAINT order_line_pkey PRIMARY KEY (ol_w_id ASC, ol_d_id ASC, ol_o_id DESC, ol_number ASC),
        CONSTRAINT order_line_ol_w_id_ol_d_id_ol_o_id_fkey FOREIGN KEY (ol_w_id, ol_d_id, ol_o_id)
            REFERENCES public."order"(o_w_id, o_d_id, o_id) NOT VALID,
        CONSTRAINT order_line_ol_supply_w_id_ol_i_id_fkey FOREIGN KEY (ol_supply_w_id, ol_i_id)
            REFERENCES public.stock(s_w_id, s_i_id) NOT VALID
    )""",
]

OUT = Path("test/test_yaml_output_tpcc.txt")
db_name = "tpcc"

def main() -> None:
    all_schemas = {}                      # full-name → TableSchema
    for ddl in EXAMPLES:
        schema = parse_ddl(ddl)          # your helper returns TableSchema
        key = schema.table_name          # keeps schema qualifier if present
        all_schemas[key] = schema

    yaml_str = ddl_to_yaml_ca(
        "",                      # ddl_text currently unused in the function
        all_schemas,
        db_name=db_name
    )
    for schema in all_schemas.values():
        print(f"Schema of: {schema.table_name}\n {str(schema)}")
        OUT.write_text(
            f"Schema of: {schema.table_name}\n {str(schema)}" , encoding="utf-8"
        )
    OUT.write_text(yaml_str, encoding="utf-8")
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] YAML written to {OUT.resolve()}")

if __name__ == "__main__":
    main()
