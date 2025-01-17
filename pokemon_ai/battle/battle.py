from pokemon_ai.classes import Status, status_names, Pokemon, Player, PokemonType, Move, Effectiveness, Item, Criticality
from pokemon_ai.utils import print_battle_screen, clear_battle_screen, prompt_multi, okay, calculate_damage, chance, \
    is_effective


class Battle:
    _PLAYER_1_ID = 1
    _PLAYER_2_ID = 2

    def __init__(self, player1: Player, player2: Player, verbose: int = 1, use_hints=False, use_revealing=True):
        """
        Initializes a battle.
        :param player1: The first player.
        :param player2: The second player.
        :param verbose: 0 for no logs. 1 for basic information only. 2 for all information.
        :param use_hints: Show hints regarding moves' supereffectivenesses in the battle screen.
        """
        self.attack_queue = []
        self.player1 = player1
        self.player2 = player2
        self.verbose = verbose
        self.started = False
        self.ended = False
        self.use_hints = use_hints
        self.turn_count = 1
        self._reveal_all(use_revealing, player1, player2)

    def play_turn(self) -> Player:
        """
        Plays one turn in the battle.
        :return: The winning player or None.
        """
        if not self.started:
            self._battle_start(self.player1, self.player2)

        if self.verbose == 1:
            print("\nTURN", self.turn_count)
            pokemon = self.player1.get_party().get_starting()
            other_pokemon = self.player2.get_party().get_starting()
            print(pokemon.get_name(), " - ", pokemon.get_hp())
            print(other_pokemon.get_name(), " - ", other_pokemon.get_hp())

        # Start two turns
        for player, opponent in [[self.player1, self.player2], [self.player2, self.player1]]:
            if self.verbose == 2:
                print_battle_screen(player, opponent)
            self._turn_start(player)
            if self.verbose == 2:
                clear_battle_screen()

        # Perform attacks and get a winner
        self._turn_perform_attacks(self.player1, self.player2)
        winner = self._check_win()
        if winner is not None:
            # Winner!
            self._alert(winner.get_name() + ' won!', self.player1, self.player2)
            return winner

        # End both players' turns and continue
        self._turn_end(self.player1)
        self._turn_end(self.player2)
        self.turn_count += 1

        return None

    def play(self) -> Player:
        """
        Plays a whole battle by running it in a loop while there is no winner.
        :return: The winning player.
        """
        self._battle_start(self.player1, self.player2)
        winner = None
        while winner is None:
            winner = self.play_turn()
        return winner

    def play_turns(self, n: int):
        """
        Plays n turns of the battle.
        :param n: Number of turns to play.
        :return: The winning player.
        """
        for _ in range(n):
            winner = self.play_turn()
            if winner is not None:
                return winner
        return None

    ##
    # Alert
    ##

    def _alert(self, message: str, *players: Player):
        """
        Alert a message that non-AI users have to respond "OK" to.
        :param message: The message to write.
        :param players: The list of players to write the message to.
        """
        if self.verbose == 2:
            for player in players:
                if not player.is_ai():
                    okay(message)
        elif self.verbose == 1:
            print(message)

    ##
    # Battle Functions
    ##

    def _battle_start(self, player1: Player, player2: Player):
        """
        Called when the battle is about to begin.
        :param player1: The first player.
        :param player2: The second player.
        """
        self.started = True

        # Assign faux IDs for keeping track
        player1._id = self._PLAYER_1_ID
        player2._id = self._PLAYER_2_ID

        # Reveal starting Pokemon
        player1.get_party().get_starting().reveal()
        player2.get_party().get_starting().reveal()

        if self.verbose >= 1:
            # Clear the terminal window
            #clear(get_terminal_dimensions()[1])
            print("")

    ##
    # Turn Functions
    ##

    def _turn_start(self, player: Player):
        """
        Called when the provided player's turn starts.
        :param player: The player whose turn it is.
        """
        if not player.is_ai():
            turn_complete = False
            while not turn_complete:
                pokemon = player.get_party().get_starting()
                move = prompt_multi('What will ' + player.get_name() + '\'s ' + pokemon.get_name() + ' do?',
                                    "Attack",
                                    "Bag",
                                    "Switch Pokemon",
                                    "Check Opponent's Pokemon",
                                    "Forfeit"
                                    )[0]
                if move == 0:
                    turn_complete = self._turn_attack(player)
                elif move == 1:
                    turn_complete = self._turn_bag(player)
                elif move == 2:
                    turn_complete = self._turn_switch_pokemon(player)
                elif move == 3:
                    turn_complete = False
                    self._turn_check_pokemon(player)
                else:
                    clear_battle_screen()
                    self._alert(player.get_name() + ' forfeits...', player)
                    exit(0)
        else:
            # AI player should make move decision based on provided objects.
            self._turn_ai(player)

    def _turn_end(self, player: Player):
        """
        Called when a turn is about to end to inflict damage from statuses and other things.
        :param player: The player to perform the calculations on.
        :return: True if the player wins, False otherwise.
        """
        # Get the Pokemon that's currently out
        pokemon = player.get_party().get_starting()

        def self_inflict(base_damage: int):
            # Performs damage calculation for self-inflicted attacks
            damage = int(pokemon.get_stats().get_attack() / base_damage)
            defense = int(pokemon.get_stats().get_defense() / base_damage * 1 / 10)
            total_damage = min(max(1, (damage - defense)), pokemon.get_hp())
            pokemon.take_damage(total_damage)
            if pokemon.is_fainted():
                self._alert(pokemon.get_name() + ' fainted!', player)
                return not self._turn_switch_pokemon(player, False)
            return False

        if pokemon.get_other_status() in [Status.POISON, Status.BAD_POISON, Status.BURN]:
            self._alert(pokemon.get_name() + ' is ' + status_names[pokemon.get_other_status()] + '.', player)

            # Increment the number of turns with the other status
            pokemon.inc_other_status_turn()

            if pokemon.get_other_status() is Status.POISON:
                damage = int(pokemon.get_base_hp() / 16)
                self._alert(pokemon.get_name() + ' took ' + str(damage) + ' damage from poison.', player)
                return self_inflict(damage)
            if pokemon.get_other_status() is Status.BAD_POISON:
                damage = int(pokemon.get_base_hp() * pokemon.get_other_status_turns() / 16)
                self._alert(pokemon.get_name() + ' took ' + str(damage) + ' damage from poison.', player)
                return self_inflict(damage)
            elif pokemon.get_other_status() is Status.BURN:
                damage = int(pokemon.get_base_hp() / 8)
                self._alert(pokemon.get_name() + ' took ' + str(damage) + ' damage from its burn.', player)
                return self_inflict(damage)

        return False

    def _turn_ai(self, player: Player):
        """
        Let's the player's AI model perform the turn.
        :param player: The player the AI plays for.
        :return: True, always, as if the model knows what it's doing.
        """
        assert player.get_model() is not None

        # Get the other player
        other_player = self.player2 if player.get_id() == self._PLAYER_1_ID else self.player1

        # Create lambda functions to be used by the model
        attack_func = lambda move: self._turn_attack(player, move)
        use_item_func = lambda item: self._turn_bag(player, item)
        switch_pokemon_at_idx_func = lambda idx: self._turn_switch_pokemon(player, False, idx)

        # Take the turn using the model
        player.get_model().take_turn(player, other_player, attack_func, use_item_func, switch_pokemon_at_idx_func)

        return True

    def _turn_attack(self, player: Player, ai_move: Move = None):
        """
        Called when the player chooses to attack.
        :param player: The player who is attacking.
        :param ai_move: The move the AI is playing.
        :return: True if the player selected an attack, False if the player chooses to go back.
        """
        pokemon = player.get_party().get_starting()
        other_player = self.player2 if player.get_id() == self._PLAYER_1_ID else self.player1
        on_pokemon = other_player.get_party().get_starting()
        move = None
        if not player.is_ai():
            if pokemon.must_struggle():
                while move is None:
                    move_idx = prompt_multi(
                        pokemon.get_name() + ' is out of usable moves.\nWould you like to use Struggle?',
                        'No (Go back)', *['Yes'])
                    if move_idx == 0:
                        return False
                    move = Pokemon.STRUGGLE
            else:
                while move is None or not move.is_available():
                    move_idx = prompt_multi('Select a move.', 'None (Go back)',
                                            *[m.get_name() + ': ' + PokemonType(m.get_type()).name.lower().capitalize() +
                                              (" (" + is_effective(m.get_type(),
                                                                   on_pokemon.get_type()).name.lower() + " damage) " if
                                               self.use_hints else "") + ', ' + str(m.get_pp()) + '/' + str(m.get_base_pp())
                                              + ' PP' for m in pokemon.get_move_bank().get_as_list()])[0]
                    if move_idx == 0:
                        return False
                    move = pokemon.get_move_bank().get_move(move_idx - 1)
                    if not move.is_available():
                        self._alert("There's no PP left for this move!", player)
        elif ai_move is not None:
            # ai_move contains the same move on another copy of the player's Pokemon, so we have to retrieve the
            # same move in the current in-game Pokemon
            if pokemon.must_struggle():
                move = Pokemon.STRUGGLE
            else:
                ai_move_name = ai_move.get_name()
                for temp_move in player.get_party().get_starting().get_move_bank().get_as_list():
                    if temp_move.get_name() == ai_move_name:
                        move = temp_move
                        break
        else:
            return False

        self._enqueue_attack(player, move)
        return True

    def _turn_bag(self, player: Player, ai_item: Item = None):
        """
        Called when the player chooses to use a bag item.
        :param player: The player who is opening the bag.
        :param ai_item: The item the AI is using.
        :return: True if the player uses a bag item, False if the player chooses to go back.
        """
        pokemon = player.get_party().get_starting()
        if not player.is_ai():
            item = prompt_multi('Use which item?', 'None (Go back)',
                                *[i.get_name() + " (" + i.get_description() + ")" for i in
                                  player.get_bag().get_as_list()])[0]
        elif ai_item is not None:
            item = ai_item
        else:
            item = 0

        if item == 0:
            return False

        item_idx = item - 1
        item = player.get_bag().get_as_list()[item_idx]

        # Use the item and remove it from the player's bag
        self._alert("%s used a %s." % (player.get_name(), item.get_name()), self.player1, self.player2)
        item.use(player, pokemon)
        player.get_bag().get_as_list().remove(item_idx)

        return True

    def _turn_switch_pokemon(self, player: Player, none_option=True, ai_pokemon_idx: int = None):
        """
        Called when the player must switch Pokemon.
        :param player: The player who is switching pokemon.
        :param none_option: Is the player allowed to go back? Aka, is there an option to choose "None"?
        :param ai_pokemon_idx: The index of the Pokemon the AI is switching out.
        :return: True if the player switches Pokemon, false otherwise.
        """
        # Get the other player
        other_player = self.player2 if player.get_id() == self._PLAYER_1_ID else self.player1

        current_pokemon = player.get_party().get_starting()
        can_switch_pokemon = not all([pokemon.is_fainted() for pokemon in player.get_party().get_as_list()])
        if not can_switch_pokemon:
            return False
        if not player.is_ai():
            while True:
                # Write the options out
                options = [p.get_name() + " (" + str(p.get_hp()) + "/" + str(p.get_base_hp()) + " HP)" for p in
                           player.get_party().get_as_list()]
                if none_option:
                    options.insert(0, 'None (Go back)')
                item = prompt_multi('Which Pokémon would you like to switch in?', *options)[0]

                # The player chooses "None"
                if none_option and item == 0:
                    return False

                # Get the Pokemon to switch in
                idx = item - bool(none_option)
                switched_pokemon = player.get_party().get_at_index(idx)

                if switched_pokemon.is_fainted():
                    self._alert(switched_pokemon.get_name() + ' has fainted.', player)
                elif idx == 0:
                    self._alert(switched_pokemon.get_name() + ' is currently in battle.', player)
                else:
                    if current_pokemon.get_status() == Status.CONFUSION:
                        current_pokemon.set_status(None)
                    switched_pokemon.reveal()
                    self._alert('Switched ' + current_pokemon.get_name() + ' with ' + switched_pokemon.get_name() + '.',
                                player)
                    self._alert(
                        player.get_name() + ' switched ' + current_pokemon.get_name() + ' with ' + switched_pokemon.get_name() + '.',
                        other_player)
                    player.get_party().make_starting(idx)
                    return True
        elif player.is_ai():
            while ai_pokemon_idx is None or ai_pokemon_idx == 0 or ai_pokemon_idx >= len(player.get_party().get_as_list()):
                ai_pokemon_idx = player.get_model().force_switch_pokemon(player.get_party())
            switched_pokemon = player.get_party().get_at_index(ai_pokemon_idx)
            player.get_party().make_starting(ai_pokemon_idx)
            if current_pokemon.get_status() == Status.CONFUSION:
                current_pokemon.set_status(None)
            switched_pokemon.reveal()
            self._alert('Switched ' + current_pokemon.get_name() + ' with ' + switched_pokemon.get_name() + '.', player)
            self._alert(
                player.get_name() + ' switched ' + current_pokemon.get_name() + ' with ' + switched_pokemon.get_name() + '.',
                other_player)
            return True
        else:
            return False

    def _turn_check_pokemon(self, player: Player):
        other_player = self.player2 if player.get_id() == self._PLAYER_1_ID else self.player1
        clear_battle_screen()
        print(str(other_player.get_party()))

    def _turn_perform_attacks(self, player_a: Player, player_b: Player):
        """
        Dequeues and performs the attacks in the attack queue.
        :param player_a: The first player to perform attacks for.
        :param player_b: The second player to perform attacks for.
        """
        for player, pokemon, move in self.attack_queue:
            if player.get_id() is player_a.get_id():
                if self._perform_attack(move, player_a, player_b, pokemon):
                    break
            elif player.get_id() is player_b.get_id():
                if self._perform_attack(move, player_b, player_a, pokemon):
                    break
        self.attack_queue = []

    def _perform_attack(self, move: Move, player: Player, on_player: Player, pokemon: Pokemon):
        """
        Performs a move by the starting Pokemon of player against the starting pokemon of on_player.
        :param move: The move player's Pokemon is performing.
        :param player: The player whose Pokemon is attacking.
        :param on_player: The player whose Pokemon is defending.
        :param pokemon: The attacking Pokemon.
        :return: Returns True if player wins, False otherwise.
        """

        if pokemon.is_fainted():
            return False

        on_pokemon = on_player.get_party().get_starting()

        def confusion():
            base_damage = 40
            damage = int(pokemon.get_stats().get_attack() / base_damage)
            defense = int(pokemon.get_stats().get_defense() / base_damage * 1 / 10)
            total_damage = max(1, damage - defense)
            pokemon.take_damage(total_damage)
            self._alert(pokemon.get_name() + ' hurt itself in its confusion.', player, on_player)
            if pokemon.is_fainted():
                self._alert(pokemon.get_name() + ' fainted!', player)
                return not self._turn_switch_pokemon(player, False)
            return False

        def paralysis():
            self._alert(pokemon.get_name() + ' is unable to move.', player, on_player)

        def infatuation():
            self._alert(pokemon.get_name() + ' is infatuated and is unable to move.', player, on_player)

        def freeze():
            self._alert(pokemon.get_name() + ' is frozen solid.', player, on_player)

        def sleep():
            self._alert(pokemon.get_name() + ' is fast asleep.', player, on_player)

        def try_attack():
            # Decrease the PP on the move
            move.dec_pp()
            move.reveal()

            # Checks to see if the attack hit
            change_of_hit = pokemon.get_stats().get_accuracy() / 100 * on_pokemon.get_stats().get_evasiveness() / 100
            did_hit = chance(change_of_hit, True, False)

            if not did_hit:
                self._alert(pokemon.get_name() + '\'s attack missed.', player, on_player)
                return False

            self._alert(player.get_name() + "'s " + pokemon.get_name() + ' used ' + move.get_name() + '!', player, on_player)

            if move.is_damaging():
                # Calculate damage
                damage, effectiveness, critical = calculate_damage(move, pokemon, on_pokemon)

                # Describe the effectiveness
                if critical == Criticality.CRITICAL and effectiveness != Effectiveness.NO_EFFECT:
                    self._alert('A critical hit!', player, on_player)
                if effectiveness == Effectiveness.NO_EFFECT:
                    self._alert('It has no effect on ' + on_pokemon.get_name() + '.', player, on_player)
                if effectiveness == Effectiveness.SUPER_EFFECTIVE:
                    self._alert('It\'s super effective!', player, on_player)
                if effectiveness == Effectiveness.NOT_EFFECTIVE:
                    self._alert('It\'s not very effective...', player, on_player)

                self._alert(on_pokemon.get_name() + ' took ' + str(damage) + ' damage.', player, on_player)

                # Lower the opposing Pokemon's HP
                on_pokemon._hp = max(0, on_pokemon.get_hp() - damage)

                # If struggle was used, lower own hp by 25% of max HP
                if move == Pokemon.STRUGGLE:
                    move.inc_pp()
                    own_damage = pokemon.get_base_hp() // 4
                    if pokemon.get_base_hp() % 4 >= 2:
                        own_damage += 1
                    pokemon._hp = max(0, pokemon.get_hp() - own_damage)
                    self._alert(pokemon.get_name() + ' was hit with recoil for ' + str(own_damage) + ' damage!')

            # If the move inflicts a status, perform the status effect
            if move.get_status_inflict():
                if move.get_status_inflict() in [Status.POISON, Status.BAD_POISON, Status.BURN]:
                    # Unlike status turns, other status turns increase in length because they don't end
                    on_pokemon.set_other_status(move.get_status_inflict())
                else:
                    on_pokemon.set_status(move.get_status_inflict())
                self._alert(on_pokemon.get_name() + ' was ' + status_names[move.get_status_inflict()], player,
                            on_player)

            # Heal the pokemon
            if move.get_base_heal() > 0:
                on_pokemon.heal(move.get_base_heal())
                self._alert(pokemon.get_name() + ' gained ' + str(move.get_base_heal()) + ' HP.', player)

            if pokemon.is_fainted():
                self._alert(pokemon.get_name() + ' fainted!')
                self._turn_switch_pokemon(player)

            # Check if the Pokemon fainted
            if on_pokemon.is_fainted():
                self._alert(on_pokemon.get_name() + ' fainted!', player, on_player)
                return not self._turn_switch_pokemon(on_player, False)

            return False

        if pokemon.get_status() not in [None, Status.POISON, Status.BAD_POISON, Status.BURN]:
            # If the Pokemon is inflicted by a status effect that impacts the chance of landing the attack,
            # perform the calculations.
            status = pokemon.get_status()
            pokemon._status_turns = max(0, pokemon.get_status_turns() - 1)
            if pokemon.get_status_turns() == 0:
                pokemon._status = None
            self._alert(pokemon.get_name() + ' is ' + status_names[status] + '.', player, on_player)
            if status is Status.CONFUSION:
                chance(1 / 3, lambda: confusion(), try_attack)
            elif status is Status.PARALYSIS:
                chance(0.25, lambda: paralysis(), try_attack)
            elif status is Status.INFATUATION:
                chance(0.5, lambda: infatuation(), try_attack)
            elif status is Status.FREEZE:
                freeze()
            elif status is Status.SLEEP:
                sleep()
        elif pokemon.get_status() is None:
            # No status effect, attempt to attack
            return try_attack()

        return False

    ##
    # Queue Functions
    ##

    def _enqueue_attack(self, player: Player, move: Move):
        """
        Enqueues an attack to be done by the player, depending on the player's Pokemon's speed.
        :param player: The player whose starter Pokemon will be attacking.
        :param move: The move to attack with.
        """
        pokemon = player.get_party().get_starting()
        attack_triple = (player, pokemon, move)
        if len(self.attack_queue) == 0:
            self.attack_queue.append(attack_triple)
        else:
            op_speed = self.attack_queue[0][1].get_stats().get_speed()
            self_speed = pokemon.get_stats().get_speed()
            if op_speed > self_speed:
                self.attack_queue.append(attack_triple)
            elif op_speed < self_speed:
                self.attack_queue.insert(0, attack_triple)
            else:
                chance(0.5, lambda: self.attack_queue.append(attack_triple),
                       lambda: self.attack_queue.insert(0, attack_triple))

    ##
    # Progress Functions
    ##

    def _check_win(self):
        """
        Returns the winner, if any.
        :return: The winning Player object.
        """
        player_1_won = all([pokemon.is_fainted() for pokemon in self.player2.get_party().get_as_list()])
        player_2_won = all([pokemon.is_fainted() for pokemon in self.player1.get_party().get_as_list()])
        if player_1_won:
            return self.player1
        elif player_2_won:
            return self.player2
        return None

    ##
    # Utility Functions
    ##

    @staticmethod
    def _reveal_all(use_revealing: bool, player1: Player, player2: Player) -> None:
        for player in [player1, player2]:
            for pkmn in player.get_party().get_as_list():
                pkmn.hide() if use_revealing else pkmn.reveal()
                for move in pkmn.get_move_bank().get_as_list():
                    move.hide() if use_revealing else move.reveal()
