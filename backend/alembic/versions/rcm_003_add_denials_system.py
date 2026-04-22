"""Add denial management and appeal system

Revision ID: rcm_003
Revises: rcm_002
Create Date: 2024-01-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'rcm_003'
down_revision = 'rcm_002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create appeal_templates table
    op.create_table(
        'appeal_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_name', sa.String(length=200), nullable=False),
        sa.Column('template_type', sa.String(length=100)),
        sa.Column('description', sa.Text()),
        sa.Column('subject', sa.String(length=500)),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('available_merge_fields', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('letterhead_template', sa.String(length=100)),
        sa.Column('signature_block', sa.Text()),
        sa.Column('times_used', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('created_by', sa.String(length=100)),
        
        sa.PrimaryKeyConstraint('id')
    )

    # Create denial_playbooks table
    op.create_table(
        'denial_playbooks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('carc_code', sa.String(length=20)),
        sa.Column('rarc_code', sa.String(length=20)),
        sa.Column('denial_category', sa.String(length=100)),
        sa.Column('playbook_name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('appeal_template_id', sa.Integer()),
        sa.Column('required_attachments', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('submission_method', sa.String(length=50)),
        sa.Column('submission_address', sa.Text()),
        sa.Column('submission_fax', sa.String(length=50)),
        sa.Column('submission_portal_url', sa.String(length=500)),
        sa.Column('typical_turnaround_days', sa.Integer()),
        sa.Column('success_rate', sa.Numeric(precision=5, scale=2)),
        sa.Column('total_appeals', sa.Integer(), server_default='0'),
        sa.Column('won_appeals', sa.Integer(), server_default='0'),
        sa.Column('staff_instructions', sa.Text()),
        sa.Column('common_pitfalls', postgresql.JSON(astext_type=sa.Text())),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['appeal_template_id'], ['appeal_templates.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_denial_playbooks_carc_code', 'denial_playbooks', ['carc_code'])
    op.create_index('ix_denial_playbooks_rarc_code', 'denial_playbooks', ['rarc_code'])
    op.create_index('ix_denial_playbooks_denial_category', 'denial_playbooks', ['denial_category'])

    # Create denial_cases table
    op.create_table(
        'denial_cases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('claim_line_id', sa.Integer()),
        sa.Column('carc_code', sa.String(length=20), nullable=False),
        sa.Column('rarc_code', sa.String(length=20)),
        sa.Column('denial_description', sa.Text()),
        sa.Column('denial_category', sa.String(length=100)),
        sa.Column('denial_subcategory', sa.String(length=100)),
        sa.Column('denied_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='new'),
        sa.Column('assigned_to', sa.String(length=100)),
        sa.Column('priority', sa.String(length=20), server_default='medium'),
        sa.Column('appeal_due_date', sa.Date()),
        sa.Column('days_until_due', sa.Integer()),
        sa.Column('playbook_id', sa.Integer()),
        sa.Column('appeal_letter_generated', sa.Boolean(), server_default='false'),
        sa.Column('appeal_letter_path', sa.String(length=1000)),
        sa.Column('appeal_submitted_date', sa.Date()),
        sa.Column('appeal_submission_method', sa.String(length=50)),
        sa.Column('appeal_tracking_number', sa.String(length=100)),
        sa.Column('appeal_response_date', sa.Date()),
        sa.Column('appeal_won', sa.Boolean()),
        sa.Column('appeal_recovery_amount', sa.Numeric(precision=10, scale=2)),
        sa.Column('root_cause', sa.Text()),
        sa.Column('preventable', sa.Boolean()),
        sa.Column('suggested_rule_update', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.text('now()')),
        sa.Column('closed_at', sa.DateTime()),
        sa.Column('created_by', sa.String(length=100)),
        
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['claim_line_id'], ['claim_lines.id']),
        sa.ForeignKeyConstraint(['playbook_id'], ['denial_playbooks.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_denial_cases_claim_id', 'denial_cases', ['claim_id'])
    op.create_index('ix_denial_cases_carc_code', 'denial_cases', ['carc_code'])
    op.create_index('ix_denial_cases_denial_category', 'denial_cases', ['denial_category'])
    op.create_index('ix_denial_cases_status', 'denial_cases', ['status'])
    op.create_index('ix_denial_cases_assigned_to', 'denial_cases', ['assigned_to'])
    op.create_index('ix_denial_cases_appeal_due_date', 'denial_cases', ['appeal_due_date'])
    op.create_index('ix_denial_cases_created_at', 'denial_cases', ['created_at'])

    # Create carc_codes reference table
    op.create_table(
        'carc_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100)),
        sa.Column('subcategory', sa.String(length=100)),
        sa.Column('default_queue', sa.String(length=100)),
        sa.Column('is_appealable', sa.Boolean(), server_default='true'),
        sa.Column('typical_success_rate', sa.Numeric(precision=5, scale=2)),
        sa.Column('common_resolution', sa.Text()),
        sa.Column('cms_reference_url', sa.String(length=500)),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_carc_codes_code', 'carc_codes', ['code'], unique=True)
    op.create_index('ix_carc_codes_category', 'carc_codes', ['category'])

    # Create rarc_codes reference table
    op.create_table(
        'rarc_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=100)),
        sa.Column('resolution_guidance', sa.Text()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_rarc_codes_code', 'rarc_codes', ['code'], unique=True)


def downgrade() -> None:
    op.drop_table('rarc_codes')
    op.drop_table('carc_codes')
    op.drop_table('denial_cases')
    op.drop_table('denial_playbooks')
    op.drop_table('appeal_templates')
    op.drop_table('claim_events')
    op.drop_table('claim_queues')

