from os import environ

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.0,
    participation_fee=0.0,
)

SESSION_CONFIGS = [
    dict(
        name='combined_public_goods',
        num_demo_participants=5,
        app_sequence=['public_goods_leader', 'public_goods_leader_variable'],
    ),
    dict(
        name='public_goods_leader',
        num_demo_participants=5,
        app_sequence=['public_goods_leader'],
    ),
    dict(
        name='public_goods_variable_leader',
        num_demo_participants=5,
        app_sequence=['public_goods_leader_variable'],
    ),
]

LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True
DEMO_PAGE_INTRO_HTML = ''

# settings.py
PARTICIPANT_FIELDS = [
    'prolific_id',
    'is_dropout',
    'needs_dropout_notice',
    'contrib_done',
    'trust_done',
    'round_ready',
    'treatment',
    'lobby_ready',
    'group_incomplete',
]

SESSION_FIELDS = [
    'leader_left',
    'last_leader_message',
    'member_left',
]

THOUSAND_SEPARATOR = ''
AUTO_TABULATE_PAYOFFS = False
ROOMS = [
    dict(
        name='classroom',
        display_name='Classroom Session',
    ),
]

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = '1234'

SECRET_KEY = 'blahblah'

INSTALLED_APPS = ['otree']