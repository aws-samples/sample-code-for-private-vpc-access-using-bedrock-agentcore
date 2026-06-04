-- Insert sample campaign data
INSERT INTO campaign (
    campaign, start_date, end_date, category_level_1, category_level_2,
    segment_id, segment_name, segment_description, total_users_in_segment,
    purchases, users_that_purchased, user_purchase_rate, total_product_sales, total_units_sold
) VALUES
    ('SPRING_SALE_2024', '2024-03-01 00:00:00', '2024-03-31 23:59:59', 'Electronics', 'Smartphones', 
     1001, 'Tech Enthusiasts', 'Users interested in latest technology', 50000, 
     2500, 1800, 0.036, 125000.50, 2500),
    
    ('SUMMER_PROMO_2024', '2024-06-01 00:00:00', '2024-06-30 23:59:59', 'Fashion', 'Summer Wear', 
     1002, 'Fashion Forward', 'Style-conscious shoppers', 75000, 
     4200, 3100, 0.041, 210000.75, 4200),
    
    ('BACK_TO_SCHOOL_2024', '2024-08-15 00:00:00', '2024-09-15 23:59:59', 'Books', 'Educational', 
     1003, 'Students & Parents', 'Back to school shoppers', 100000, 
     8500, 6200, 0.062, 340000.00, 8500),
    
    ('BLACK_FRIDAY_2024', '2024-11-29 00:00:00', '2024-11-29 23:59:59', 'Electronics', 'TVs & Home Theater', 
     1004, 'Deal Hunters', 'Price-sensitive shoppers', 200000, 
     15000, 12000, 0.060, 1500000.00, 15000),
    
    ('CYBER_MONDAY_2024', '2024-12-02 00:00:00', '2024-12-02 23:59:59', 'Electronics', 'Computers', 
     1005, 'Tech Professionals', 'Professional tech buyers', 80000, 
     5600, 4200, 0.053, 560000.00, 5600),
    
    ('HOLIDAY_GIFT_2024', '2024-12-01 00:00:00', '2024-12-24 23:59:59', 'Toys', 'Kids & Family', 
     1006, 'Gift Givers', 'Holiday shoppers', 150000, 
     12000, 9500, 0.063, 480000.00, 12000),
    
    ('NEW_YEAR_FITNESS_2025', '2025-01-01 00:00:00', '2025-01-31 23:59:59', 'Sports', 'Fitness Equipment', 
     1007, 'Health Conscious', 'Fitness enthusiasts', 60000, 
     3200, 2400, 0.040, 192000.00, 3200),
    
    ('VALENTINES_DAY_2025', '2025-02-01 00:00:00', '2025-02-14 23:59:59', 'Jewelry', 'Gifts', 
     1008, 'Romantic Shoppers', 'Valentine gift buyers', 45000, 
     2800, 2200, 0.049, 280000.00, 2800),
    
    ('SPRING_GARDEN_2025', '2025-03-15 00:00:00', '2025-04-30 23:59:59', 'Home & Garden', 'Outdoor', 
     1009, 'Gardening Enthusiasts', 'Home improvement shoppers', 55000, 
     3100, 2300, 0.042, 155000.00, 3100),
    
    ('PRIME_DAY_2025', '2025-07-15 00:00:00', '2025-07-16 23:59:59', 'All Categories', 'Prime Exclusive', 
     1010, 'Prime Members', 'Amazon Prime subscribers', 300000, 
     45000, 35000, 0.117, 4500000.00, 45000)
ON CONFLICT (campaign) DO NOTHING;

-- Verify the data was inserted
SELECT COUNT(*) as total_campaigns FROM campaign;
