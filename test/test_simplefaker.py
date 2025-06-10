#!/usr/bin/env python3
"""
Smoke-test for dbworkload.utils.simplefaker_ca.SimpleFakerCA.

• builds a tiny YAML workload entirely in-memory, including a **composite-FK** table
• writes the resulting CSVs to ./out
• shows the first few rows so you can eyeball them
"""

from __future__ import annotations
import pathlib, shutil, yaml
from dbworkload.utils.simplefaker_ca import SimpleFakerCA


# ─── Minimal YAML workload ─────────────────────────────────────────────────
#
#   public.countries   (50 rows, UNIQUE code & name)
#   public.users       (50 rows, FK → countries.code, fan-out 2:1)
#   public.user_logins (20 rows, COMPOSITE FK → users.(id,email))
#
'''MINI_YAML = """
public__countries:
- count: 50
  sort-by: []
  pk: [code]
  columns:
    code:
      type: string
      args: {seed: 1, min: 2, max: 2, null_pct: 0.0}
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    name:
      type: string
      args: {seed: 2, min: 5, max: 15, null_pct: 0.0}
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: true

public__users:
- count: 50
  sort-by: []
  pk: [id]
  columns:
    id:
      type: sequence
      args: {start: 1, seed: 3, null_pct: 0.0}
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    country_code:
      type: string
      args: {seed: 4, min: 2, max: 2, null_pct: 0.0}
      fk: public__countries.code
      hasForeignKey: true
      fk_mode: block
      fanout: 2
      parent_seed: 1
      isPrimaryKey: false
      isUnique: false
    email:
      type: string
      args: {seed: 5, min: 5, max: 15, null_pct: 0.0}
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: true

public__user_logins:
- count: 50
  sort-by: []
  pk: [session_id]
  columns:
    session_id:
      type: uuid
      args: {seed: 10, null_pct: 0.0}
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    user_id:
      type: integer
      args: {seed: 11, min: 1, max: 1000, null_pct: 0.0}
      fk: public__users.id
      hasForeignKey: true
      composite_id: 1         
      fk_mode: block
      fanout: 2
      parent_seed: 3
      isPrimaryKey: false
      isUnique: false
    user_email:
      type: string
      args: {seed: 12, min: 5, max: 15, null_pct: 0.0}
      fk: public__users.email
      hasForeignKey: true
      composite_id: 1          
      fk_mode: block
      fanout: 2
      parent_seed: 5
      isPrimaryKey: false
      isUnique: false
    login_ts:
      type: timestamp
      args: {seed: 13, start: '2000-01-01', end: '2025-01-01', format: '%Y-%m-%d %H:%M:%S.%f', null_pct: 0.0}
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false

"""
'''

MINI_YAML = """
public__warehouse:
- count: 100
  sort-by: []
  pk:
  - w_id
  columns:
    w_id:
      type: sequence
      args:
        start: 1
        seed: 66
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    w_name:
      type: string
      args:
        seed: 32
        min: 1
        max: 10
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_street_1:
      type: string
      args:
        seed: 54
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_street_2:
      type: string
      args:
        seed: 93
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_city:
      type: string
      args:
        seed: 83
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_state:
      type: string
      args:
        seed: 18
        min: 2
        max: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_zip:
      type: string
      args:
        seed: 80
        min: 9
        max: 9
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_tax:
      type: float
      args:
        seed: 62
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    w_ytd:
      type: float
      args:
        seed: 69
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
public__district:
- count: 100
  sort-by: []
  pk:
  - d_w_id
  - d_id
  columns:
    d_id:
      type: sequence
      args:
        start: 1
        seed: 48
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    d_w_id:
      type: sequence
      args:
        start: 1
        seed: 5
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__warehouse.w_id
      fk_mode: block
      fanout: 10
      parent_seed: 66
    d_name:
      type: string
      args:
        seed: 57
        min: 1
        max: 10
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_street_1:
      type: string
      args:
        seed: 85
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_street_2:
      type: string
      args:
        seed: 65
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_city:
      type: string
      args:
        seed: 58
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_state:
      type: string
      args:
        seed: 74
        min: 2
        max: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_zip:
      type: string
      args:
        seed: 18
        min: 9
        max: 9
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_tax:
      type: float
      args:
        seed: 11
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_ytd:
      type: float
      args:
        seed: 46
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    d_next_o_id:
      type: integer
      args:
        seed: 82
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
public__customer:
- count: 100
  sort-by: []
  pk:
  - c_w_id
  - c_d_id
  - c_id
  columns:
    c_id:
      type: sequence
      args:
        start: 1
        seed: 73
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    c_d_id:
      type: sequence
      args:
        start: 1
        seed: 69
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__district.d_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 48
    c_w_id:
      type: sequence
      args:
        start: 1
        seed: 17
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__district.d_w_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 5
    c_first:
      type: string
      args:
        seed: 75
        min: 1
        max: 16
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_middle:
      type: string
      args:
        seed: 8
        min: 2
        max: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_last:
      type: string
      args:
        seed: 100
        min: 1
        max: 16
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_street_1:
      type: string
      args:
        seed: 35
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_street_2:
      type: string
      args:
        seed: 77
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_city:
      type: string
      args:
        seed: 25
        min: 1
        max: 20
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_state:
      type: string
      args:
        seed: 21
        min: 2
        max: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_zip:
      type: string
      args:
        seed: 60
        min: 9
        max: 9
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_phone:
      type: string
      args:
        seed: 19
        min: 16
        max: 16
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_since:
      type: timestamp
      args:
        seed: 95
        start: '2000-01-01'
        end: '2025-01-01'
        format: '%Y-%m-%d %H:%M:%S.%f'
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_credit:
      type: string
      args:
        seed: 22
        min: 2
        max: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_credit_lim:
      type: float
      args:
        seed: 31
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_discount:
      type: float
      args:
        seed: 7
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_balance:
      type: float
      args:
        seed: 99
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_ytd_payment:
      type: float
      args:
        seed: 85
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_payment_cnt:
      type: integer
      args:
        seed: 63
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_delivery_cnt:
      type: integer
      args:
        seed: 58
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    c_data:
      type: string
      args:
        seed: 71
        min: 1
        max: 500
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
public__history:
- count: 100
  sort-by: []
  pk:
  - h_w_id
  - rowid
  columns:
    rowid:
      type: uuid
      args:
        seed: 47
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    h_c_id:
      type: integer
      args:
        seed: 87
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__customer.c_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 73
    h_c_d_id:
      type: integer
      args:
        seed: 26
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__customer.c_d_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 69
    h_c_w_id:
      type: integer
      args:
        seed: 53
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__customer.c_w_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 17
    h_d_id:
      type: integer
      args:
        seed: 10
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__district.d_id
      composite_id: 2
      fk_mode: block
      fanout: 10
      parent_seed: 48
    h_w_id:
      type: sequence
      args:
        start: 1
        seed: 54
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__district.d_w_id
      composite_id: 2
      fk_mode: block
      fanout: 10
      parent_seed: 5
    h_date:
      type: timestamp
      args:
        seed: 46
        start: '2000-01-01'
        end: '2025-01-01'
        format: '%Y-%m-%d %H:%M:%S.%f'
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    h_amount:
      type: float
      args:
        seed: 43
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    h_data:
      type: string
      args:
        seed: 14
        min: 1
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
public__order:
- count: 100
  sort-by: []
  pk:
  - o_w_id
  - o_d_id
  - o_id
  columns:
    o_id:
      type: sequence
      args:
        start: 1
        seed: 33
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    o_d_id:
      type: sequence
      args:
        start: 1
        seed: 54
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__customer.c_d_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 69
    o_w_id:
      type: sequence
      args:
        start: 1
        seed: 63
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__customer.c_w_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 17
    o_c_id:
      type: integer
      args:
        seed: 82
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__customer.c_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 73
    o_entry_d:
      type: timestamp
      args:
        seed: 62
        start: '2000-01-01'
        end: '2025-01-01'
        format: '%Y-%m-%d %H:%M:%S.%f'
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    o_carrier_id:
      type: integer
      args:
        seed: 89
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    o_ol_cnt:
      type: integer
      args:
        seed: 51
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    o_all_local:
      type: integer
      args:
        seed: 46
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
  unique:
  - - o_w_id
    - o_d_id
    - o_c_id
    - o_id
public__new_order:
- count: 100
  sort-by: []
  pk:
  - no_w_id
  - no_d_id
  - no_o_id
  columns:
    no_o_id:
      type: sequence
      args:
        start: 1
        seed: 71
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__order.o_id
      composite_id: 1
      fk_mode: block
      fanout: 1
      parent_seed: 33
    no_d_id:
      type: sequence
      args:
        start: 1
        seed: 75
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__order.o_d_id
      composite_id: 1
      fk_mode: block
      fanout: 1
      parent_seed: 54
    no_w_id:
      type: sequence
      args:
        start: 1
        seed: 57
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__order.o_w_id
      composite_id: 1
      fk_mode: block
      fanout: 1
      parent_seed: 63
public__item:
- count: 100
  sort-by: []
  pk:
  - i_id
  columns:
    i_id:
      type: sequence
      args:
        start: 1
        seed: 65
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    i_im_id:
      type: integer
      args:
        seed: 79
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    i_name:
      type: string
      args:
        seed: 62
        min: 1
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    i_price:
      type: float
      args:
        seed: 20
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    i_data:
      type: string
      args:
        seed: 26
        min: 1
        max: 50
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
public__stock:
- count: 100
  sort-by: []
  pk:
  - s_w_id
  - s_i_id
  columns:
    s_i_id:
      type: sequence
      args:
        start: 1
        seed: 8
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__item.i_id
      fk_mode: block
      fanout: 1
      parent_seed: 65
    s_w_id:
      type: sequence
      args:
        start: 1
        seed: 85
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__warehouse.w_id
      fk_mode: block
      fanout: 1
      parent_seed: 66
    s_quantity:
      type: integer
      args:
        seed: 5
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_01:
      type: string
      args:
        seed: 23
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_02:
      type: string
      args:
        seed: 75
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_03:
      type: string
      args:
        seed: 2
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_04:
      type: string
      args:
        seed: 51
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_05:
      type: string
      args:
        seed: 8
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_06:
      type: string
      args:
        seed: 16
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_07:
      type: string
      args:
        seed: 7
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_08:
      type: string
      args:
        seed: 0
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_09:
      type: string
      args:
        seed: 12
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_dist_10:
      type: string
      args:
        seed: 83
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_ytd:
      type: integer
      args:
        seed: 15
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_order_cnt:
      type: integer
      args:
        seed: 63
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_remote_cnt:
      type: integer
      args:
        seed: 17
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    s_data:
      type: string
      args:
        seed: 62
        min: 1
        max: 50
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
public__order_line:
- count: 100
  sort-by: []
  pk:
  - ol_w_id
  - ol_d_id
  - ol_o_id
  - ol_number
  columns:
    ol_o_id:
      type: sequence
      args:
        start: 1
        seed: 40
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__order.o_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 33
    ol_d_id:
      type: sequence
      args:
        start: 1
        seed: 57
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__order.o_d_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 54
    ol_w_id:
      type: sequence
      args:
        start: 1
        seed: 21
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: true
      isUnique: true
      fk: public__order.o_w_id
      composite_id: 1
      fk_mode: block
      fanout: 10
      parent_seed: 63
    ol_number:
      type: sequence
      args:
        start: 1
        seed: 4
        null_pct: 0.0
      hasForeignKey: false
      isPrimaryKey: true
      isUnique: true
    ol_i_id:
      type: integer
      args:
        seed: 73
        min: -2147483648
        max: 2147483647
        null_pct: 0.0
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__stock.s_i_id
      composite_id: 2
      fk_mode: block
      fanout: 10
      parent_seed: 8
    ol_supply_w_id:
      type: integer
      args:
        seed: 84
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: true
      isPrimaryKey: false
      isUnique: false
      fk: public__stock.s_w_id
      composite_id: 2
      fk_mode: block
      fanout: 10
      parent_seed: 85
    ol_delivery_d:
      type: timestamp
      args:
        seed: 41
        start: '2000-01-01'
        end: '2025-01-01'
        format: '%Y-%m-%d %H:%M:%S.%f'
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    ol_quantity:
      type: integer
      args:
        seed: 20
        min: -2147483648
        max: 2147483647
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    ol_amount:
      type: float
      args:
        seed: 78
        min: 0
        max: 1000000
        round: 2
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
    ol_dist_info:
      type: string
      args:
        seed: 26
        min: 24
        max: 24
        null_pct: 0.1
      hasForeignKey: false
      isPrimaryKey: false
      isUnique: false
"""

def main() -> None:
    base_dir = pathlib.Path(__file__).resolve().parent
    out_dir  = "test" / base_dir / "out"

    # fresh output directory
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir()

    load_dict = yaml.safe_load(MINI_YAML)

    print("➡  Generating CSVs into", out_dir)
    SimpleFakerCA(csv_max_rows=500).generate(
        load=load_dict,
        exec_threads=1,          # single process – but 2 worker threads in-process
        csv_dir=str(out_dir),
        delimiter=",",
        compression=None,
    )

    # show a teaser of each produced file
    print("\nProduced files:")
    for csv_path in sorted(out_dir.iterdir()):
        print("──", csv_path.name)
        with csv_path.open() as fh:
            for i, line in zip(range(3), fh):      # first 3 lines
                print("   ", line.rstrip())
        print("   …")
    print("✅  Done.")


if __name__ == "__main__":
    main()
