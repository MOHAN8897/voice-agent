BEGIN;

-- Running upgrade 039_native_billing_rates -> 040_vobiz_tenant_subaccounts

CREATE TABLE vobiz_subaccounts (
    tenant_id UUID NOT NULL, 
    auth_id VARCHAR(80), 
    encrypted_auth_token TEXT, 
    parent_auth_id VARCHAR(80), 
    account_enabled BOOLEAN NOT NULL, 
    application_id VARCHAR(80), 
    kyc_session_id VARCHAR(80), 
    encrypted_kyc_url TEXT, 
    kyc_session_expires_at TIMESTAMP WITH TIME ZONE, 
    kyc_session_status VARCHAR(32), 
    business_type VARCHAR(40) NOT NULL, 
    account_name VARCHAR(255) NOT NULL, 
    account_email VARCHAR(320) NOT NULL, 
    provisioning_status VARCHAR(32) NOT NULL, 
    kyc_status VARCHAR(32) NOT NULL, 
    kyc_calls_blocked BOOLEAN NOT NULL, 
    verifications JSONB NOT NULL, 
    last_status_sync_at TIMESTAMP WITH TIME ZONE, 
    last_error_code VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (tenant_id), 
    CONSTRAINT uq_vobiz_subaccounts_auth_id UNIQUE (auth_id), 
    FOREIGN KEY(tenant_id) REFERENCES tenants (tenant_id) ON DELETE CASCADE
);

ALTER TABLE number_purchases ADD COLUMN provider VARCHAR(30);

ALTER TABLE number_purchases ADD COLUMN carrier_number_id VARCHAR(255);

ALTER TABLE phone_numbers ADD COLUMN vobiz_account_scope VARCHAR(16);

ALTER TABLE phone_numbers ADD COLUMN vobiz_account_tenant_id UUID;

UPDATE alembic_version SET version_num='040_vobiz_tenant_subaccounts' WHERE alembic_version.version_num = '039_native_billing_rates';

COMMIT;

