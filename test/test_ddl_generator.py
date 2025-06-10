# test_ddl_generator.py

from dbworkload.models.ddl_generator import (
    parse_ddl,
    anonymize_schema,
    anonymize_create_table,
)

OUTPUT_FILE = "test/test_output_ddl_tpcc.txt"

'''# 🎯 Add your DDL examples here to stress-test parsing & anonymization
examples = [
    #ref_data table
    """CREATE TABLE IF NOT EXISTS public.ref_data (
        acc_no INT8 NOT NULL,
        external_ref_id UUID NULL,
        created_time TIMESTAMPTZ NULL,
        acc_details VARCHAR NULL,
        CONSTRAINT ref_data_pkey PRIMARY KEY (acc_no ASC)
    )""",

    # orders table
    """CREATE TABLE IF NOT EXISTS public.orders (
        acc_no INT8 NOT NULL,
        id UUID NOT NULL DEFAULT gen_random_uuid(),
        status VARCHAR NOT NULL,
        amount DECIMAL(15,2) NULL,
        ts TIMESTAMPTZ NULL DEFAULT now():::TIMESTAMPTZ,
        CONSTRAINT pk PRIMARY KEY (acc_no ASC, id ASC)
    )""",

    # 1) Inline PRIMARY KEY on a single column
    """CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT UNIQUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""",

    # 2) Table-level UNIQUE and CHECK constraints
    """CREATE TABLE IF NOT EXISTS products (
        sku VARCHAR(20) NOT NULL,
        name TEXT NOT NULL,
        price DECIMAL(10,4) NOT NULL CHECK (price > 0),
        quality VARCHAR(12) NOT NULL,
        CONSTRAINT products_pk PRIMARY KEY (sku),
        UNIQUE (name),
        CHECK (char_length(sku) = 10)
    )""",

    # 3) Inline foreign key + table-level composite FK
    """CREATE TABLE IF NOT EXISTS order_items (
        order_id INT NOT NULL REFERENCES orders(id),
        line_no INT NOT NULL,
        product_sku VARCHAR(20) NOT NULL,
        qty INT NOT NULL DEFAULT 1,
        CONSTRAINT items_pk PRIMARY KEY (order_id, line_no),
        CONSTRAINT fk_item_product FOREIGN KEY (product_sku) REFERENCES products(sku)
    )""",

    # 4) Quoted identifiers, mixed case, special chars
    """CREATE TABLE IF NOT EXISTS "My-Schema"."My-Table" (
        "Col-1" INT NOT NULL DEFAULT 42,
        "Col-2" TEXT NULL,
        CONSTRAINT "PK_My-Table" PRIMARY KEY ("Col-1")
    )""",

    # 5) CHECK with nested parentheses and boolean defaults
    """CREATE TABLE IF NOT EXISTS flags (
        flag_name TEXT NOT NULL,
        is_active BOOL NOT NULL DEFAULT true,
        flags_mask INT NOT NULL DEFAULT (0) CHECK ((flags_mask & 1) = 0),
        PRIMARY KEY (flag_name)
    )""",

    # 6) Array type and composite default
    """CREATE TABLE IF NOT EXISTS tags (
        id UUID NOT NULL DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        aliases TEXT[] NULL DEFAULT ARRAY[]::TEXT[],
        CONSTRAINT tags_pk PRIMARY KEY (id)
    )""",

    # 7) No IF NOT EXISTS, schema qualification
    """CREATE TABLE IF NOT EXISTS audit.log_entries (
        entry_id UUID NOT NULL DEFAULT uuid_generate_v4(),
        user_id INT NOT NULL,
        action TEXT NOT NULL,
        ts TIMESTAMPTZ NOT NULL DEFAULT now(),
        FOREIGN KEY (user_id, action) REFERENCES users(id,email)
    )""",

    # 8) Table with composite UNIQUE constraint
    """CREATE TABLE foo (
        a INT NOT NULL,
        b INT NOT NULL,
        c INT NOT NULL,
        CONSTRAINT uq_foo_ab UNIQUE(a, b),
        CONSTRAINT uq_foo_c UNIQUE(c)
    )""",
]
'''
examples = [
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



def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for ddl in examples:
            out.write(f"IN :  {ddl}\n\n")

            # 1) parse into TableSchema
            try:
                schema = parse_ddl(ddl)
                out.write("Parsed schema:\n")
                out.write(str(schema) + "\n")
            except Exception as e:
                out.write(f"[ERROR parsing DDL] {e}\n\n")
                out.write("-" * 60 + "\n\n")
                continue

            # 2) anonymize schema (single-table dict) and then anonymize the CREATE statement
            tbl_key = schema.table_name.split(".")[-1]
            schemas_dict = {tbl_key: schema}
            anon_schemas, mapping, _ = anonymize_schema(schemas_dict, db_alias="db")

            # try:
            #     anon_stmt, _, _ = anonymize_create_table(ddl, mapping)
            #     out.write("Anonymized DDL:\n")
            #     out.write(anon_stmt.strip() + "\n")
            # except Exception as e:
            #     out.write(f"[ERROR anonymizing DDL] {e}\n")

            out.write("\n" + "-" * 60 + "\n\n")

    print(f"Done! Check {OUTPUT_FILE} for results.")

if __name__ == "__main__":
    main()
