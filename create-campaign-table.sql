-- Create campaign table
CREATE TABLE IF NOT EXISTS campaign (
    campaign VARCHAR(255) PRIMARY KEY,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    category_level_1 VARCHAR(100),
    category_level_2 VARCHAR(100),
    segment_id INTEGER NOT NULL,
    segment_name VARCHAR(100),
    segment_description TEXT,
    total_users_in_segment INTEGER,
    purchases INTEGER,
    users_that_purchased INTEGER,
    user_purchase_rate DOUBLE PRECISION,
    total_product_sales DOUBLE PRECISION,
    total_units_sold INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX idx_campaign_dates ON campaign(start_date, end_date);
CREATE INDEX idx_campaign_segment ON campaign(segment_id);
CREATE INDEX idx_campaign_categories ON campaign(category_level_1, category_level_2);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_campaign_updated_at BEFORE UPDATE ON campaign
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create read-only user for MCP Server (defense-in-depth: prevents write operations at database level)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mcp_readonly') THEN
        CREATE USER mcp_readonly WITH PASSWORD 'mcp_readonly_temp';
    END IF;
END
$$;
GRANT CONNECT ON DATABASE campaigndb TO mcp_readonly;
GRANT USAGE ON SCHEMA public TO mcp_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_readonly;
