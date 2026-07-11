-- ==================== 零售业务数据库建表语句 ====================
-- TextSQL-Agent 测试数据

-- 门店表
CREATE TABLE IF NOT EXISTS stores (
    store_id SERIAL PRIMARY KEY,
    store_name VARCHAR(64) NOT NULL,
    city VARCHAR(32) NOT NULL,
    area_sqm DECIMAL(8,2),
    open_date DATE,
    manager_name VARCHAR(32)
);

-- 商品表
CREATE TABLE IF NOT EXISTS products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,
    cost_price DECIMAL(10,2),
    retail_price DECIMAL(10,2),
    supplier VARCHAR(64),
    brand VARCHAR(64)
);

-- 客户表
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    customer_name VARCHAR(64),
    customer_phone VARCHAR(20),
    customer_idcard VARCHAR(20),
    membership_level VARCHAR(16) DEFAULT '普通',
    register_date DATE DEFAULT CURRENT_DATE,
    total_spent DECIMAL(14,2) DEFAULT 0
);

-- 销售订单主表
CREATE TABLE IF NOT EXISTS sales_orders (
    order_id BIGSERIAL PRIMARY KEY,
    store_id INT REFERENCES stores(store_id),
    customer_id BIGINT REFERENCES customers(customer_id),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(12,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    payment_method VARCHAR(32),
    order_status VARCHAR(16) DEFAULT 'completed'
);

-- 订单明细表
CREATE TABLE IF NOT EXISTS order_items (
    item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT REFERENCES sales_orders(order_id),
    product_id INT REFERENCES products(product_id),
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL
);

-- 库存表
CREATE TABLE IF NOT EXISTS inventory (
    inventory_id BIGSERIAL PRIMARY KEY,
    store_id INT REFERENCES stores(store_id),
    product_id INT REFERENCES products(product_id),
    stock_quantity INT NOT NULL DEFAULT 0,
    safety_stock INT DEFAULT 10,
    last_restock_date DATE
);

-- 财务汇总表
CREATE TABLE IF NOT EXISTS finance_summary (
    summary_id BIGSERIAL PRIMARY KEY,
    store_id INT REFERENCES stores(store_id),
    month DATE NOT NULL,
    total_revenue DECIMAL(14,2),
    total_cost DECIMAL(14,2),
    gross_profit DECIMAL(14,2),
    profit_margin DECIMAL(6,4),
    operating_expense DECIMAL(12,2)
);

-- ==================== 测试数据 ====================

-- 门店
INSERT INTO stores (store_name, city, area_sqm, open_date, manager_name) VALUES
('北京朝阳店', '北京', 320.5, '2023-01-15', '张伟'),
('上海浦东店', '上海', 450.0, '2022-11-20', '李娜'),
('广州天河店', '广州', 280.3, '2023-03-08', '王强'),
('深圳南山店', '深圳', 380.8, '2022-09-01', '赵敏'),
('成都锦江店', '成都', 250.0, '2023-06-10', '陈杰');

-- 商品
INSERT INTO products (product_name, category, cost_price, retail_price, supplier, brand) VALUES
('iPhone 15 Pro', '数码', 6500.00, 8999.00, '苹果中国', 'Apple'),
('小米14', '数码', 2800.00, 3999.00, '小米科技', 'Xiaomi'),
('华为Mate60', '数码', 3500.00, 4999.00, '华为终端', 'HUAWEI'),
('AirPods Pro', '配件', 1200.00, 1899.00, '苹果中国', 'Apple'),
('小米手环8', '配件', 180.00, 249.00, '小米科技', 'Xiaomi'),
('联想笔记本', '电脑', 3500.00, 5499.00, '联想集团', 'Lenovo'),
('戴尔显示器', '电脑', 1200.00, 1899.00, '戴尔中国', 'DELL'),
('罗技鼠标', '配件', 80.00, 159.00, '罗技中国', 'Logitech');

-- 客户
INSERT INTO customers (customer_name, customer_phone, customer_idcard, membership_level, register_date, total_spent) VALUES
('刘小明', '13800138001', '110101199001011234', '黄金', '2023-01-20', 25600.50),
('王小华', '13900139002', '310101199202022345', '白银', '2023-02-15', 12300.00),
('张小三', '13700137003', '440101199303033456', '普通', '2023-03-10', 3600.00),
('李小四', '13600136004', '510101199404044567', '黄金', '2022-12-05', 45800.00),
('赵小五', '13500135005', '120101199505055678', '白银', '2023-04-01', 8900.00);

-- 销售订单
INSERT INTO sales_orders (store_id, customer_id, order_date, total_amount, discount_amount, payment_method, order_status) VALUES
(1, 1, '2024-06-01 10:30:00', 8999.00, 0, '微信支付', 'completed'),
(1, 2, '2024-06-02 14:20:00', 3999.00, 200, '支付宝', 'completed'),
(2, 3, '2024-06-03 09:15:00', 1899.00, 0, '微信支付', 'completed'),
(2, 4, '2024-06-04 16:45:00', 5499.00, 300, '银行卡', 'completed'),
(3, 5, '2024-06-05 11:00:00', 249.00, 0, '微信支付', 'completed'),
(3, 1, '2024-06-06 13:30:00', 4999.00, 100, '支付宝', 'completed'),
(4, 2, '2024-06-07 15:20:00', 1899.00, 0, '微信支付', 'completed'),
(4, 3, '2024-06-08 10:10:00', 159.00, 0, '现金', 'completed'),
(5, 4, '2024-06-09 14:00:00', 8999.00, 0, '支付宝', 'completed'),
(5, 5, '2024-06-10 09:45:00', 3999.00, 200, '微信支付', 'completed'),
(1, 1, '2024-07-01 11:30:00', 1899.00, 0, '微信支付', 'completed'),
(2, 3, '2024-07-02 14:20:00', 5499.00, 0, '支付宝', 'completed'),
(3, 5, '2024-07-03 10:00:00', 249.00, 0, '微信支付', 'completed'),
(4, 1, '2024-07-04 16:15:00', 4999.00, 100, '银行卡', 'completed'),
(5, 2, '2024-07-05 13:45:00', 8999.00, 0, '支付宝', 'completed');

-- 订单明细
INSERT INTO order_items (order_id, product_id, quantity, unit_price, subtotal) VALUES
(1, 1, 1, 8999.00, 8999.00),
(2, 2, 1, 3999.00, 3999.00),
(3, 4, 1, 1899.00, 1899.00),
(4, 6, 1, 5499.00, 5499.00),
(5, 5, 1, 249.00, 249.00),
(6, 3, 1, 4999.00, 4999.00),
(7, 7, 1, 1899.00, 1899.00),
(8, 8, 1, 159.00, 159.00),
(9, 1, 1, 8999.00, 8999.00),
(10, 2, 1, 3999.00, 3999.00),
(11, 4, 1, 1899.00, 1899.00),
(12, 6, 1, 5499.00, 5499.00),
(13, 5, 1, 249.00, 249.00),
(14, 3, 1, 4999.00, 4999.00),
(15, 1, 1, 8999.00, 8999.00);

-- 库存
INSERT INTO inventory (store_id, product_id, stock_quantity, safety_stock, last_restock_date) VALUES
(1, 1, 45, 10, '2024-06-20'),
(1, 2, 30, 8, '2024-06-20'),
(1, 3, 5, 10, '2024-06-15'),
(1, 4, 60, 15, '2024-06-22'),
(2, 1, 50, 10, '2024-06-18'),
(2, 2, 8, 8, '2024-06-18'),
(2, 5, 120, 20, '2024-06-25'),
(3, 1, 3, 10, '2024-06-10'),
(3, 3, 25, 10, '2024-06-20'),
(4, 6, 15, 5, '2024-06-22'),
(4, 7, 8, 10, '2024-06-15'),
(5, 1, 0, 10, '2024-06-05'),
(5, 4, 40, 15, '2024-06-28');

-- 财务汇总
INSERT INTO finance_summary (store_id, month, total_revenue, total_cost, gross_profit, profit_margin, operating_expense) VALUES
(1, '2024-06-01', 12998.00, 9300.00, 3698.00, 0.2845, 2000.00),
(2, '2024-06-01', 7398.00, 4700.00, 2698.00, 0.3647, 1500.00),
(3, '2024-06-01', 5248.00, 3500.00, 1748.00, 0.3331, 1200.00),
(4, '2024-06-01', 2058.00, 1280.00, 778.00, 0.3780, 800.00),
(5, '2024-06-01', 12998.00, 6500.00, 6498.00, 0.5000, 1800.00),
(1, '2024-07-01', 1899.00, 1200.00, 699.00, 0.3681, 500.00),
(2, '2024-07-01', 5499.00, 3500.00, 1999.00, 0.3635, 800.00),
(3, '2024-07-01', 249.00, 180.00, 69.00, 0.2771, 200.00),
(4, '2024-07-01', 4999.00, 3500.00, 1499.00, 0.2999, 600.00),
(5, '2024-07-01', 8999.00, 6500.00, 2499.00, 0.2777, 700.00);
