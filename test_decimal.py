import decimal

pw_sum = float(decimal.Decimal(100) or 0)
pc_sum = float(decimal.Decimal(50) or 0)
pe_sum = float(decimal.Decimal(20) or 0)

DEMO_CONSUMER_GOODS_CONSUMPTION = {
    "pop_working": 1.0 / 80000,
    "pop_children": 1.2 / 80000,
    "pop_elderly": 2.0 / 80000,
}

total_cg_need = (
    pw_sum
    * DEMO_CONSUMER_GOODS_CONSUMPTION["pop_working"]
    + pc_sum
    * DEMO_CONSUMER_GOODS_CONSUMPTION["pop_children"]
    + pe_sum
    * DEMO_CONSUMER_GOODS_CONSUMPTION["pop_elderly"]
)
print("total_cg_need:", total_cg_need)
