from otree.api import (
    cu,
    models,
    widgets,
    BaseConstants,
    BaseSubsession,
    BaseGroup,
    BasePlayer,
    WaitPage,   # 👈 ADD THIS
    Page,
)
import time 

class C(BaseConstants):
    NAME_IN_URL = 'public_goods_leader'
    PLAYERS_PER_GROUP = 5
    NUM_ROUNDS = 10
    NUM_MEMBERS = 4

    MULTIPLIER = 1.8
    LEADER_FIXED_PAYMENT = 20
    MESSAGE_TIME_SECONDS = 120
    CONTRIBUTION_TIME_SECONDS = 120

    MEMBER_ENDOWMENT = 10
    TRUST_MIN = 0
    TRUST_MAX = 10

    LEADER_ROLE = 'Leader'
    MEMBER_ROLE = 'Member'


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    total_contribution = models.IntegerField()
    shared_pot = models.CurrencyField()
    individual_share = models.CurrencyField()
    wait_contributions_start = models.FloatField(initial=0)  # 👈 rename for clarity
    wait_leader_start = models.FloatField(initial=0)          # 👈 add this too


class Player(BasePlayer):
    prolific_id = models.StringField(label="Please enter your Prolific ID")

    contribution = models.IntegerField(
        initial=0,
        label='How much will you contribute to the group account?',
        max=C.MEMBER_ENDOWMENT,
        min=0,
    )

    leader_message = models.LongStringField(
        label='Your message to the group members (you have 2 minutes)'
    )

    comp_attempts = models.IntegerField(initial=0)

    comp_q1 = models.IntegerField(
        label="1. Each token a group member contributes to the Group Account reduces their Private Account by how many tokens?",
        min=0,
        max=100,
    )

    comp_q2 = models.IntegerField(
        label="2. If all 4 group members contribute 10 tokens each, how many tokens does each member earn?",
        min=0,
        max=100,
    )

    comp_q3 = models.StringField(
        label="3. If all group members contribute 10 tokens each to the Group Account:",
        choices=[
            ['a', "a. Different group members would receive different earnings."],
            ['b', "b. Each group member’s earnings would be lower than if no one contributed."],
            ['c', "c. Each group member’s earnings would be higher than if no one contributed."],
        ],
        widget=widgets.RadioSelect,
    )

    comp_q4 = models.StringField(
        label="4. The leader’s payoff in this experiment consists of:",
        choices=[
            ['a', "a. A fixed payment only."],
            ['b', "b. A fixed payment and a performance-based payment."],
        ],
        widget=widgets.RadioSelect,
    )

    trust_leader = models.IntegerField(
        label="How much do you trust the Leader in this group?",
        min=0,
        max=10,
    )

    trust_members = models.IntegerField(
        label="How much do you trust the other Members in this group?",
        min=0,
        max=10,
    )

    still_here = models.StringField(
        label="✔ I'm still here",
        choices=[['yes', "Yes, I'm still here"]],
        widget=widgets.RadioSelect,
        blank=True,
    )

    def role(self):
        return C.LEADER_ROLE if self.id_in_group == 1 else C.MEMBER_ROLE


def creating_session(subsession):
    if subsession.round_number == 1:
        for player in subsession.get_players():
            player.participant.is_dropout = False
            player.participant.needs_dropout_notice = False
            player.participant.prolific_id = ''
    
    # Reset per-round flags for active players only
    for player in subsession.get_players():
        # Only reset flags for non-dropout players
        if not player.participant.is_dropout:
            player.participant.contrib_done = False
            player.participant.trust_done = False
            player.participant.round_ready = False

    # Reset session-level dropout flags each round
    subsession.session.leader_left = False
    subsession.session.last_leader_message = ''
    subsession.session.member_left = False


def get_dropout_notice(player):
    active_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE and not p.participant.is_dropout]
    num_members = len(active_members)

    if player.session.leader_left:
        last_msg = player.session.last_leader_message or ''
        member_notice = ''
        if player.session.member_left:
            if num_members == 0:
                member_notice = ' All group members have left the game.'
            elif num_members == 1:
                member_notice = ' A group member has left the game. This group has been reduced to 1 member and no leader.'
            else:
                member_notice = f' A group member has left the game. This group has been reduced to {num_members} members and no leader.'
        if last_msg:
            return f"Your leader has left the game.{member_notice} This was their last message: {last_msg}"
        return f"Your leader has left the game.{member_notice}"

    if player.session.member_left:
        if num_members == 0:
            return "All group members have left the game."
        elif num_members == 1:
            return "A group member has left the game. This group has been reduced to 1 member and 1 leader."
        else:
            return f"A group member has left the game. This group has been reduced to {num_members} members and 1 leader."

    return ''


def group_should_end(player):
    active_members = [
        p for p in player.group.get_players()
        if p.role() == C.MEMBER_ROLE and not p.participant.is_dropout
    ]
    return len(active_members) <= 1


def mark_dropout(player):
    player.participant.is_dropout = True
    player.participant.needs_dropout_notice = True
    player.participant.contrib_done = True
    player.participant.trust_done = True
    player.participant.round_ready = True

    if player.role() == C.LEADER_ROLE:
        player.session.leader_left = True
        
        # Find the most recent non-blank message from any round
        last_message = ''
        for p in player.in_all_rounds():
            msg = p.field_maybe_none('leader_message')
            if msg and msg.strip():
                last_message = msg
                break
        
        player.session.last_leader_message = last_message
    else:
        player.session.member_left = True


def detect_unresponsive(player, flag_name, wait_key_prefix, grace_seconds=30):
    """After grace_seconds of waiting, mark active players who haven't set their flag as dropouts."""
    key = f'{wait_key_prefix}_g{player.group.id_in_subsession}_r{player.round_number}'
    active_players = [
        p for p in player.group.get_players()
        if not p.participant.is_dropout
    ]
    all_set = all(getattr(p.participant, flag_name, False) for p in active_players)
    if all_set:
        return
    if key not in player.session.vars:
        player.session.vars[key] = time.time()
    elif time.time() - player.session.vars[key] > grace_seconds:
        for p in active_players:
            if not getattr(p.participant, flag_name, False):
                mark_dropout(p)


def calculate_payoffs(group: Group):
    active_members = [
        p for p in group.get_players()
        if p.role() == C.MEMBER_ROLE and not p.participant.is_dropout
    ]

    group.total_contribution = sum(p.contribution for p in active_members)
    group.shared_pot = cu(group.total_contribution * C.MULTIPLIER)

    if active_members:
        group.individual_share = group.shared_pot / len(active_members)
    else:
        group.individual_share = cu(0)

    for p in group.get_players():
        if p.participant.is_dropout:
            p.payoff = cu(0)
            continue

        if p.role() == C.LEADER_ROLE:
            # Leader still gets fixed payment even if all members drop out
            p.payoff = cu(C.LEADER_FIXED_PAYMENT)
        else:
            # Member payoff: tokens kept + share of multiplied pot
            p.payoff = cu(C.MEMBER_ENDOWMENT - p.contribution) + group.individual_share


class ProlificID(Page):
    form_model = 'player'
    form_fields = ['prolific_id']

    @staticmethod
    def is_displayed(player):
        return player.round_number == 1

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.prolific_id = player.prolific_id


class NoDeceptionPolicy(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Instructions(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Instructions2(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Instructions3(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Instructions4(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Instructions5(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Instructions6(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1


class Examples(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player):
        leader_examples = [
            dict(
                num=1,
                contributions=[4, 3, 5, 8],
                total=20,
                multiplied=36,
                member_share=9,
                leader_payoff=10,
            ),
            dict(
                num=2,
                contributions=[10, 0, 0, 0],
                total=10,
                multiplied=18,
                member_share=4.5,
                leader_payoff=20,
            ),
            dict(
                num=3,
                contributions=[6, 6, 6, 6],
                total=24,
                multiplied=43.2,
                member_share=10.8,
                leader_payoff=20,
            ),
        ]

        examples = [
            dict(
                num=1,
                your_contribution=4,
                others=[3, 5, 8],
                total=20,
                multiplied=36,
                share=9,
                kept=6,
                payoff=15,
            ),
            dict(
                num=2,
                your_contribution=10,
                others=[0, 0, 0],
                total=10,
                multiplied=18,
                share=4.5,
                kept=0,
                payoff=4.5,
            ),
            dict(
                num=3,
                your_contribution=0,
                others=[6, 6, 6],
                total=18,
                multiplied=32.4,
                share=8.1,
                kept=10,
                payoff=18.1,
            ),
        ]

        return dict(
            leader_examples=leader_examples,
            examples=examples,
        )


class Comprehension(Page):
    form_model = 'player'
    form_fields = ['comp_q1', 'comp_q2', 'comp_q3', 'comp_q4']

    @staticmethod
    def is_displayed(player):
        return player.round_number == 1

    @staticmethod
    def error_message(player, values):
        wrong = {}
        if values['comp_q1'] != 1:
            wrong['comp_q1'] = "Incorrect. Each contributed token reduces the private account by 1."
        if values['comp_q2'] != 18:
            wrong['comp_q2'] = "Incorrect. Multiply total contributions by 1.8 and divide equally."
        if values['comp_q3'] != 'c':
            wrong['comp_q3'] = "Incorrect. Contributions increase earnings for everyone."
        if values['comp_q4'] != 'a':
            wrong['comp_q4'] = "Incorrect. The leader receives only a fixed payment."

        if wrong:
            player.comp_attempts += 1
            if player.comp_attempts < 3:
                return {k: 'Incorrect. Please try again.' for k in wrong}
            return wrong
        return {}


class ComprehensionWaitPage(WaitPage):
    wait_for_all_groups = False
    
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1
    
    @staticmethod
    def after_all_players_arrive(group):
        pass


class Introduction(Page):
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player):
        return dict(is_leader=player.role() == C.LEADER_ROLE)


class ReadyWaitPage(WaitPage):
    wait_for_all_groups = False
    
    @staticmethod
    def is_displayed(player):
        return player.round_number == 1
    
    @staticmethod
    def after_all_players_arrive(group):
        pass


class RoundStartWaitPage(Page):
    form_model = 'player'
    form_fields = []
    timer_text = 'Time left for group members to join:'

    @staticmethod
    def is_displayed(player):
        return not player.participant.is_dropout and not group_should_end(player)

    @staticmethod
    def get_timeout_seconds(player):
        return 60

    @staticmethod
    def live_method(player, data):
        player.participant.round_ready = True

        if group_should_end(player):
            return {0: dict(all_done=True)}

        detect_unresponsive(player, 'round_ready', 'round_wait', 30)

        active_players = [
            p for p in player.group.get_players()
            if not p.participant.is_dropout
        ]
        all_ready = all(p.participant.round_ready for p in active_players)
        return {0: dict(all_done=all_ready)}

    @staticmethod
    def before_next_page(player, timeout_happened):
        if timeout_happened:
            for p in player.group.get_players():
                if not p.participant.is_dropout and not p.participant.round_ready:
                    mark_dropout(p)


class LeaderMessage(Page):
    form_model = 'player'
    form_fields = ['leader_message']

    @staticmethod
    def is_displayed(player):
        return (
            player.role() == C.LEADER_ROLE
            and not player.participant.is_dropout
            and not group_should_end(player)
            and not player.session.leader_left
        )

    @staticmethod
    def get_timeout_seconds(player):
        return C.MESSAGE_TIME_SECONDS

    @staticmethod
    def vars_for_template(player):
        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members = [p for p in all_members if not p.participant.is_dropout]
        dropout_count = len(all_members) - len(active_members)
        
        return dict(
            member_left=player.session.member_left,
            active_member_count=len(active_members),
            dropout_count=dropout_count,
            original_member_count=C.NUM_MEMBERS,
        )

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.contrib_done = False
        if timeout_happened:
            mark_dropout(player)


class WaitForLeader(Page):
    form_model = 'player'
    form_fields = []
    timer_text = 'Time left for the leader to write their message:'

    @staticmethod
    def is_displayed(player):
        return (
            player.role() == C.MEMBER_ROLE
            and not player.participant.is_dropout
            and not group_should_end(player)
        )

    @staticmethod
    def get_timeout_seconds(player):
        return C.MESSAGE_TIME_SECONDS

    @staticmethod
    def vars_for_template(player):
        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members = [p for p in all_members if not p.participant.is_dropout]
        dropout_count = len(all_members) - len(active_members)
        
        return dict(
            member_left=player.session.member_left,
            active_member_count=len(active_members),
            dropout_count=dropout_count,
            original_member_count=C.NUM_MEMBERS,
        )

    @staticmethod
    def live_method(player, data):
        if group_should_end(player):
            return {0: {"ready": True, "notice": "Too many group members have left the game. The experiment will now end."}}

        leader = player.group.get_player_by_role(C.LEADER_ROLE)
        leader_msg = leader.field_maybe_none('leader_message')
        leader_done = (
            not leader.participant.is_dropout
            and leader_msg is not None
            and leader_msg != ''
        )

        # Check if any other members are still active and waiting
        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members_waiting = [
            p for p in all_members 
            if not p.participant.is_dropout and p.id_in_group != player.id_in_group
        ]
        
        # If no other active members are waiting, we can proceed
        all_others_dropped = len(active_members_waiting) == 0

        notice = ''
        if player.session.leader_left:
            notice = "Your leader has left the game."
        elif player.session.member_left and all_others_dropped:
            notice = "All other members have left the game."

        return {0: {"ready": leader_done or player.session.leader_left or all_others_dropped, "notice": notice}}

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.contrib_done = False

        if timeout_happened:
            mark_dropout(player)
        leader = player.group.get_player_by_role(C.LEADER_ROLE)
        leader_msg = leader.field_maybe_none('leader_message')
        if not leader.participant.is_dropout and not leader_msg:
            mark_dropout(leader)

class ViewMessageAndContribute(Page):
    form_model = 'player'
    form_fields = ['contribution', 'still_here']

    @staticmethod
    def is_displayed(player):
        return (
            player.role() == C.MEMBER_ROLE
            and not player.participant.is_dropout
            and not group_should_end(player)
        )

    @staticmethod
    def get_timeout_seconds(player):
        return 30

    @staticmethod
    def vars_for_template(player):
        if player.session.leader_left:
            leader_message = player.session.last_leader_message or ''
        else:
            leader = player.group.get_player_by_role(C.LEADER_ROLE)
            leader_msg = leader.field_maybe_none('leader_message')
            leader_message = leader_msg or ''

        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members = [p for p in all_members if not p.participant.is_dropout]
        dropout_count = len(all_members) - len(active_members)
        
        return dict(
            leader_message=leader_message,
            leader_left=player.session.leader_left,
            member_left=player.session.member_left,
            active_member_count=len(active_members),
            dropout_count=dropout_count,
            original_member_count=C.NUM_MEMBERS,
        )

    @staticmethod
    def error_message(player, values):
        errors = {}
        if values.get('still_here') != 'yes':
            errors['still_here'] = (
                "If you do not confirm that you are still here, "
                "you will be exited from the study."
            )
        return errors

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.contrib_done = True

        if timeout_happened:
            mark_dropout(player)
        leader = player.group.get_player_by_role(C.LEADER_ROLE)
        leader_msg = leader.field_maybe_none('leader_message')
        if not getattr(leader.participant, 'is_dropout', False) and not leader_msg:
            mark_dropout(leader)



class WaitForContributions(Page):
    form_model = 'player'
    form_fields = []
    timer_text = 'Time left for group members to contribute:'

    @staticmethod
    def is_displayed(player):
        return not player.participant.is_dropout and not group_should_end(player)

    @staticmethod
    def get_timeout_seconds(player):
        return C.CONTRIBUTION_TIME_SECONDS + 5

    @staticmethod
    def live_method(player, data):
        if group_should_end(player):
            return {0: dict(all_done=True)}

        detect_unresponsive(player, 'contrib_done', 'contrib_wait', 45)

        active_members = [
            p for p in player.group.get_players()
            if p.role() == C.MEMBER_ROLE and not p.participant.is_dropout
        ]
        all_done = all(p.participant.contrib_done for p in active_members)

        if all_done and player.group.field_maybe_none('total_contribution') is None:
            calculate_payoffs(player.group)

        return {0: dict(all_done=all_done)}

    @staticmethod
    def before_next_page(player, timeout_happened):
        if player.group.field_maybe_none('total_contribution') is None:
            calculate_payoffs(player.group)


class ResultsWaitPage(Page):
    form_model = 'player'
    form_fields = []
    timer_text = 'Time left for results to be calculated:'

    @staticmethod
    def is_displayed(player):
        return not player.participant.is_dropout and not group_should_end(player)

    @staticmethod
    def get_timeout_seconds(player):
        return 30

    @staticmethod
    def live_method(player, data):
        if group_should_end(player):
            return {0: dict(all_done=True)}

        detect_unresponsive(player, 'contrib_done', 'results_wait', 15)

        active_members = [
            p for p in player.group.get_players()
            if p.role() == C.MEMBER_ROLE and not p.participant.is_dropout
        ]
        all_done = all(p.participant.contrib_done for p in active_members)

        if all_done and player.group.field_maybe_none('total_contribution') is None:
            calculate_payoffs(player.group)

        return {0: dict(all_done=all_done)}


class Results(Page):
    timer_text = 'Time left to view results (page will automatically continue to trust ratings):'

    @staticmethod
    def is_displayed(player):
        return not player.participant.is_dropout and not group_should_end(player)
    
    @staticmethod
    def get_timeout_seconds(player):
        return 20

    @staticmethod
    def vars_for_template(player):
        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members = [p for p in all_members if not p.participant.is_dropout]
        dropout_count = len(all_members) - len(active_members)
        
        # Safety: calculate payoffs if not yet done
        if player.group.field_maybe_none('total_contribution') is None:
            calculate_payoffs(player.group)
        
        return dict(
            total_contribution=player.group.total_contribution,
            shared_pot=player.group.shared_pot,
            individual_share=player.group.individual_share,
            is_leader=player.role() == C.LEADER_ROLE,
            tokens_kept=C.MEMBER_ENDOWMENT - player.contribution,
            payoff=player.payoff,
            dropout_notice=get_dropout_notice(player),
            active_member_count=len(active_members),
            dropout_count=dropout_count,
            original_member_count=C.NUM_MEMBERS,
        )

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.trust_done = False

class LeaderTrustRating(Page):
    form_model = 'player'
    form_fields = ['trust_members', 'still_here']

    @staticmethod
    def is_displayed(player):
        return (
            player.role() == C.LEADER_ROLE
            and not player.participant.is_dropout
            and not group_should_end(player)
        )

    @staticmethod
    def get_timeout_seconds(player):
        return 60

    @staticmethod
    def vars_for_template(player):
        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members = [p for p in all_members if not p.participant.is_dropout]
        member_dropout_count = len(all_members) - len(active_members)
        return dict(
            leader_left=player.session.leader_left,
            member_left=player.session.member_left,
            member_dropout_count=member_dropout_count,
            active_member_count=len(active_members),
        )

    @staticmethod
    def error_message(player, values):
        errors = {}
        if values.get('still_here') != 'yes':
            errors['still_here'] = (
                "If you do not confirm that you are still here, "
                "you will be exited from the study."
            )
        return errors

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.trust_done = True
        if timeout_happened:
            mark_dropout(player)


class MemberTrustRating(Page):
    form_model = 'player'
    form_fields = ['trust_leader', 'trust_members', 'still_here']

    @staticmethod
    def is_displayed(player):
        return (
            player.role() == C.MEMBER_ROLE
            and not player.participant.is_dropout
            and not group_should_end(player)
        )

    @staticmethod
    def get_timeout_seconds(player):
        return 60

    @staticmethod
    def vars_for_template(player):
        all_members = [p for p in player.group.get_players() if p.role() == C.MEMBER_ROLE]
        active_members = [p for p in all_members if not p.participant.is_dropout]
        member_dropout_count = len(all_members) - len(active_members)
        return dict(
            leader_left=player.session.leader_left,
            member_left=player.session.member_left,
            member_dropout_count=member_dropout_count,
            active_member_count=len(active_members),
        )

    @staticmethod
    def error_message(player, values):
        errors = {}
        if values.get('still_here') != 'yes':
            errors['still_here'] = (
                "If you do not confirm that you are still here, "
                "you will be exited from the study."
            )
        return errors

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.trust_done = True
        if timeout_happened:
            mark_dropout(player)


class TrustRatingsWaitPage(Page):
    form_model = 'player'
    form_fields = []
    timer_text = 'Time left for trust ratings to be submitted:'

    @staticmethod
    def is_displayed(player):
        return not player.participant.is_dropout and not group_should_end(player)

    @staticmethod
    def get_timeout_seconds(player):
        return 70

    @staticmethod
    def live_method(player, data):
        if group_should_end(player):
            return {0: dict(all_done=True)}

        detect_unresponsive(player, 'trust_done', 'trust_wait', 75)

        active_players = [
            p for p in player.group.get_players()
            if not p.participant.is_dropout
        ]
        all_done = all(p.participant.trust_done for p in active_players)
        return {0: dict(all_done=all_done)}


class Completion(Page):
    @staticmethod
    def is_displayed(player):
        return (
            player.round_number == C.NUM_ROUNDS
            and not player.participant.is_dropout
            and not group_should_end(player)
        )

    @staticmethod
    def vars_for_template(player):
        completion_code = 'CAHCFER6'
        prolific_completion_url = f'https://app.prolific.co/submissions/complete?cc={completion_code}'

        return dict(
            prolific_url=prolific_completion_url,
            completion_code=completion_code,
        )


class ExitNotice(Page):
    @staticmethod
    def is_displayed(player):
        return player.participant.is_dropout or group_should_end(player)

    @staticmethod
    def vars_for_template(player):
        completion_code = 'CAHCFER6'
        prolific_completion_url = f'https://app.prolific.co/submissions/complete?cc={completion_code}'

        if player.participant.is_dropout:
            return dict(
                exit_title="You have left this experiment.",
                exit_message="Your response was not completed in time, so your participation has ended for this study.",
                exit_note="If this was not expected, please contact the researcher.",
                completion_code=completion_code,
                prolific_url=prolific_completion_url,
            )

        return dict(
            exit_title="This experiment has ended.",
            exit_message="Three group members have left the experiment, so the session cannot continue.",
            exit_note="You will not continue to the next round.",
            completion_code=completion_code,
            prolific_url=prolific_completion_url,
        )


page_sequence = [
    ProlificID,
    NoDeceptionPolicy,
    Instructions,
    Instructions2,
    Instructions3,
    Instructions4,
    Instructions5,
    Instructions6,
    Examples,
    Comprehension,
    ComprehensionWaitPage,
    Introduction,
    ReadyWaitPage,
    RoundStartWaitPage,
    LeaderMessage,
    WaitForLeader,
    ViewMessageAndContribute,
    WaitForContributions,
    Results,
    LeaderTrustRating,
    MemberTrustRating,
    TrustRatingsWaitPage,
    ExitNotice,
    Completion,
]