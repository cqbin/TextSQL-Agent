"""
Skill 分层路由模块
按业务域组织数据表和指标，避免全库检索
"""
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class TableMeta:
    """数据表元数据"""
    table_name: str
    description: str
    domain: str                    # sales / inventory / finance / customer
    columns: list[dict] = field(default_factory=list)
    sensitive_level: str = "low"   # low / medium / high
    joins: list[str] = field(default_factory=list)  # 可关联的表


# 业务域 -> 表映射
DOMAIN_TABLES: dict[str, list[TableMeta]] = {
    "sales": [
        TableMeta(
            table_name="sales_orders",
            description="销售订单主表，记录每笔订单的金额、时间、门店",
            domain="sales",
            sensitive_level="low",
            columns=[
                {"name": "order_id", "type": "bigint", "desc": "订单ID"},
                {"name": "store_id", "type": "int", "desc": "门店ID"},
                {"name": "order_date", "type": "date", "desc": "下单日期"},
                {"name": "total_amount", "type": "decimal(12,2)", "desc": "订单总金额"},
                {"name": "discount_amount", "type": "decimal(10,2)", "desc": "折扣金额"},
                {"name": "payment_method", "type": "varchar(32)", "desc": "支付方式"},
            ],
            joins=["order_items", "stores", "customers"],
        ),
        TableMeta(
            table_name="order_items",
            description="订单明细表，记录每笔订单中的商品和数量",
            domain="sales",
            sensitive_level="low",
            columns=[
                {"name": "item_id", "type": "bigint", "desc": "明细ID"},
                {"name": "order_id", "type": "bigint", "desc": "订单ID"},
                {"name": "product_id", "type": "int", "desc": "商品ID"},
                {"name": "quantity", "type": "int", "desc": "购买数量"},
                {"name": "unit_price", "type": "decimal(10,2)", "desc": "单价"},
                {"name": "subtotal", "type": "decimal(12,2)", "desc": "小计"},
            ],
            joins=["sales_orders", "products"],
        ),
        TableMeta(
            table_name="stores",
            description="门店信息表",
            domain="sales",
            sensitive_level="low",
            columns=[
                {"name": "store_id", "type": "int", "desc": "门店ID"},
                {"name": "store_name", "type": "varchar(64)", "desc": "门店名称"},
                {"name": "city", "type": "varchar(32)", "desc": "所在城市"},
                {"name": "area_sqm", "type": "decimal(8,2)", "desc": "门店面积（平方米）"},
            ],
            joins=["sales_orders"],
        ),
    ],
    "inventory": [
        TableMeta(
            table_name="inventory",
            description="库存表，记录各门店各商品的实时库存",
            domain="inventory",
            sensitive_level="low",
            columns=[
                {"name": "inventory_id", "type": "bigint", "desc": "库存记录ID"},
                {"name": "store_id", "type": "int", "desc": "门店ID"},
                {"name": "product_id", "type": "int", "desc": "商品ID"},
                {"name": "stock_quantity", "type": "int", "desc": "库存数量"},
                {"name": "safety_stock", "type": "int", "desc": "安全库存"},
                {"name": "last_restock_date", "type": "date", "desc": "最近补货日期"},
            ],
            joins=["products", "stores"],
        ),
        TableMeta(
            table_name="products",
            description="商品信息表",
            domain="inventory",
            sensitive_level="medium",
            columns=[
                {"name": "product_id", "type": "int", "desc": "商品ID"},
                {"name": "product_name", "type": "varchar(128)", "desc": "商品名称"},
                {"name": "category", "type": "varchar(32)", "desc": "品类"},
                {"name": "cost_price", "type": "decimal(10,2)", "desc": "成本价", "sensitive": True},
                {"name": "retail_price", "type": "decimal(10,2)", "desc": "零售价"},
                {"name": "supplier", "type": "varchar(64)", "desc": "供应商"},
            ],
            joins=["order_items", "inventory"],
        ),
    ],
    "finance": [
        TableMeta(
            table_name="finance_summary",
            description="财务汇总表，按月汇总各门店收入、成本、毛利",
            domain="finance",
            sensitive_level="high",
            columns=[
                {"name": "summary_id", "type": "bigint", "desc": "汇总ID"},
                {"name": "store_id", "type": "int", "desc": "门店ID"},
                {"name": "month", "type": "date", "desc": "月份"},
                {"name": "total_revenue", "type": "decimal(14,2)", "desc": "总收入"},
                {"name": "total_cost", "type": "decimal(14,2)", "desc": "总成本", "sensitive": True},
                {"name": "gross_profit", "type": "decimal(14,2)", "desc": "毛利润", "sensitive": True},
                {"name": "profit_margin", "type": "decimal(6,4)", "desc": "毛利率", "sensitive": True},
                {"name": "operating_expense", "type": "decimal(12,2)", "desc": "运营费用"},
            ],
            joins=["stores"],
        ),
        TableMeta(
            table_name="customers",
            description="客户信息表",
            domain="finance",
            sensitive_level="high",
            columns=[
                {"name": "customer_id", "type": "bigint", "desc": "客户ID"},
                {"name": "customer_name", "type": "varchar(64)", "desc": "客户姓名"},
                {"name": "customer_phone", "type": "varchar(20)", "desc": "手机号", "sensitive": True},
                {"name": "customer_idcard", "type": "varchar(20)", "desc": "身份证号", "sensitive": True},
                {"name": "membership_level", "type": "varchar(16)", "desc": "会员等级"},
                {"name": "total_spent", "type": "decimal(14,2)", "desc": "累计消费"},
            ],
            joins=["sales_orders"],
        ),
    ],
    "customer": [
        TableMeta(
            table_name="customers",
            description="客户信息表",
            domain="customer",
            sensitive_level="high",
            columns=[
                {"name": "customer_id", "type": "bigint", "desc": "客户ID"},
                {"name": "customer_name", "type": "varchar(64)", "desc": "客户姓名"},
                {"name": "customer_phone", "type": "varchar(20)", "desc": "手机号", "sensitive": True},
                {"name": "membership_level", "type": "varchar(16)", "desc": "会员等级"},
                {"name": "total_spent", "type": "decimal(14,2)", "desc": "累计消费"},
                {"name": "register_date", "type": "date", "desc": "注册日期"},
            ],
            joins=["sales_orders"],
        ),
    ],
}


class SkillRouter:
    """
    Skill 分层路由
    第一层：按业务域分流（sales/inventory/finance/customer）
    第二层：在对应域内召回具体数据表
    """

    def __init__(self):
        self.domain_tables = DOMAIN_TABLES

    def get_tables_by_domain(self, domain: str) -> list[TableMeta]:
        """根据业务域获取可用数据表"""
        return self.domain_tables.get(domain, [])

    def get_all_domains(self) -> list[str]:
        """获取所有业务域"""
        return list(self.domain_tables.keys())

    def get_table_by_name(self, table_name: str) -> Optional[TableMeta]:
        """跨域查找表"""
        for tables in self.domain_tables.values():
            for t in tables:
                if t.table_name == table_name:
                    return t
        return None

    def get_sensitive_fields(self, domain: str) -> list[str]:
        """获取域内敏感字段"""
        tables = self.get_tables_by_domain(domain)
        sensitive = []
        for t in tables:
            for col in t.columns:
                if col.get("sensitive"):
                    sensitive.append(col["name"])
        return sensitive
