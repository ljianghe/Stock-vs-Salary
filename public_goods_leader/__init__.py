
from otree.api import (
    Currency,
    cu,
    currency_range,
    models,
    widgets,
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    ExtraModel,
    WaitPage,
    Page,
    read_csv,
)

import units
import shared_out

doc = ''
class C(BaseConstants):
    # built-in constants
    NAME_IN_URL = 'public_goods_leader'
    PLAYERS_PER_GROUP = 5
    NUM_ROUNDS = 1
    # user-defined constants
    MULTIPLIER = 1.8
    LEADER_FIXED_PAYMENT = 20
    MESSAGE_TIME_SECONDS = 120
    NUM_MEMBERS = 4
    MEMBER_ENDOWMENT = 10
    ROLE_1 = 'Leader'
    ROLE_2 = 'Member'
    ROLE_3 = 'Member'
    ROLE_4 = 'Member'
    ROLE_5 = 'Member'
    TRUST_MIN = 0
    TRUST_MAX = 10
class Subsession(BaseSubsession):
    pass
class Group(BaseGroup):
    total_contribution = models.IntegerField()
    shared_pot = models.CurrencyField()
    individual_share = models.CurrencyField()
class Player(BasePlayer):

    prolific_id = models.StringField(label="Please enter your Prolific ID")

    contribution = models.IntegerField(
        initial=0,
        label='How much will you contribute to the group account?',
        max=C.MEMBER_ENDOWMENT,
        min=0
    )


    leader_message = models.LongStringField(
        label='Your message to the group members (you have 2 minutes)'
    )

    # Comprehension Questions

    comp_q1 = models.IntegerField(
        label="1. Each token a group member contributes to the Group Account reduces their Private Account by tokens:",
        min=0,
        max=100
    )

    comp_q2 = models.IntegerField(
        label="2. If all group members contribute 10 tokens each to the Group Account, each group member earns tokens:",
        min=0,
        max=100
    )

    comp_q3 = models.StringField(
        label="3. If all group members contribute 10 tokens each to the Group Account:",
        choices=[
            ['a', "a. Different group members would receive different earnings."],
            ['b', "b. Each group member’s earnings would be lower than if no one contributed."],
            ['c', "c. Each group member’s earnings would be higher than if no one contributed."]
        ],
        widget=widgets.RadioSelect
    )

    comp_q4 = models.StringField(
        label="4. The leader’s payoff in this experiment consists of:",
        choices=[
            ['a', "a. A fixed payment only."],
            ['b', "b. A fixed payment and a performance-based payment."]
        ],
        widget=widgets.RadioSelect
    )

    def role(self):
        if self.id_in_group == 1:
            return 'Leader'
        else:
            return 'Member'
    trust_leader = models.IntegerField(
    label="How much do you trust the Leader in this group?",
    min=0,
    max=10
    )
    trust_members = models.IntegerField(
    label="How much do you trust the other Members in this group?",
    min=0,
    max=10
    )
# the below function(s) are user-defined, not called by oTree
# <helper-functions>
def calculate_payoffs(group: Group):
    members = [p for p in group.get_players() if p.role() == 'Member']

    group.total_contribution = sum(p.contribution for p in members)
    group.shared_pot = cu(group.total_contribution * C.MULTIPLIER)

    if len(members) > 0:
        group.individual_share = group.shared_pot / len(members)
    else:
        group.individual_share = cu(0)

    for p in group.get_players():
        if p.role() == 'Leader':
            p.participant.payoff += cu(C.LEADER_FIXED_PAYMENT)
        else:
            p.participant.payoff += (
                cu(C.MEMBER_ENDOWMENT - p.contribution)
                + group.individual_share
            )
# </helper-functions>
class Instructions(Page):
    form_model = 'player'
class Instructions2(Page):
    form_model = 'player'
class Instructions3(Page):
    form_model = 'player'
class Instructions4(Page):
    form_model = 'player'
class Instructions5(Page):
    form_model = 'player'
class Instructions6(Page):
    form_model = 'player'
        
class Comprehension(Page):
    form_model = 'player'
    form_fields = ['comp_q1', 'comp_q2', 'comp_q3', 'comp_q4']

    @staticmethod
    def error_message(player, values):
        errors = {}

        if values['comp_q1'] != 1:
            errors['comp_q1'] = "Incorrect. Each contributed token reduces the private account by 1."

        if values['comp_q2'] != 18:
            errors['comp_q2'] = "Incorrect. Multiply total contributions by 1.8 and divide equally."

        if values['comp_q3'] != 'c':
            errors['comp_q3'] = "Incorrect. Contributions increase earnings for everyone."

        if values['comp_q4'] != 'a':
            errors['comp_q4'] = "Incorrect. The leader receives only a fixed payment."

        return errors
    
class Introduction(Page):
    form_model = 'player'
    @staticmethod
    def vars_for_template(player: Player):
        return dict(is_leader=player.role() == 'Leader')
class LeaderMessage(Page):
    form_model = 'player'
    form_fields = ['leader_message']
    @staticmethod
    def is_displayed(player: Player):
        return player.role() == 'Leader'
    @staticmethod
    def get_timeout_seconds(player: Player):
        return C.MESSAGE_TIME_SECONDS
class WaitForLeader(WaitPage):
    pass
class ViewMessageAndContribute(Page):
    form_model = 'player'
    form_fields = ['contribution']
    @staticmethod
    def is_displayed(player: Player):
        return player.role() == 'Member'
    @staticmethod
    def vars_for_template(player: Player):
        leader = player.group.get_player_by_role('Leader')
        return dict(leader_message=leader.leader_message)
class WaitForContributions(WaitPage):
    wait_for_all_groups = False
    @staticmethod
    def after_all_players_arrive(group: Group):
        calculate_payoffs(group)
class Results(Page):
    form_model = 'player'

    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            total_contribution=player.group.total_contribution,
            shared_pot=player.group.shared_pot,
            individual_share=player.group.individual_share,
            is_leader=player.role() == 'Leader',
            tokens_kept=C.MEMBER_ENDOWMENT - player.contribution,
            payoff=player.participant.payoff
        )
class TrustRating(Page):
    form_model = 'player'
    form_fields = ['trust_leader', 'trust_members']

class Completion(Page):
    @staticmethod
    def vars_for_template(player: Player):
        completion_code = 'CAHCFER6'  # CHANGE THIS
        prolific_completion_url = f'https://app.prolific.co/submissions/complete?cc={completion_code}'

        return dict(
            prolific_url=prolific_completion_url,
            completion_code=completion_code
        )

class ProlificID(Page):
    form_model = 'player'
    form_fields = ['prolific_id']

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        player.participant.prolific_id = player.prolific_id

class NoDeceptionPolicy(Page):
    pass

page_sequence = [ProlificID, NoDeceptionPolicy, Instructions, Instructions2, Instructions3, Instructions4, Instructions5, Instructions6, Comprehension, Introduction, LeaderMessage, WaitForLeader, ViewMessageAndContribute, WaitForContributions, Results, TrustRating, Completion]
