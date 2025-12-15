import random

# TODO: get nation names from DB, get amount of fighters and bombers
# from DB, add infra damage, make aircraft consume resources
# TODO: figure out how calculate bomber and fighter losses separately


# print statements
def ground_attack(
    nat1_name: str,
    nat2_name: str,
    nat1_fighters: int,
    nat2_fighters: int,
    Nat1Bomb: int,
    Nat2Bomb: int,
) -> str:
    nat1_roll_wins = 0
    nat2_roll_wins = 0

    Nat1 = nat1_fighters
    Nat2 = nat2_fighters

    for _roll in range(0, 3):
        nat1_roll = random.randint(1, max(1, Nat1 + 5 * Nat1Bomb))
        nat2_roll = random.randint(1, max(1, Nat2 + 5 * Nat2Bomb))
        print(
            (
                "Dogfight rolls: Nat1=%s (fighters=%s, bombers=%s), "
                "Nat2=%s (fighters=%s, bombers=%s)"
            )
            % (nat1_roll, Nat1, Nat1Bomb, nat2_roll, Nat2, Nat2Bomb)
        )
        # difference between the two rolls
        difference = abs(nat1_roll - nat2_roll)

        if nat1_roll > nat2_roll:
            nat1_roll_wins += 1
            # subtract difference from the nations maximum if they rolled lower
            Nat2 -= difference
            # calulates bomber losses
            Bombloss = random.randint(1, max(1, Nat1Bomb // 5)) * 5
            Nat1Bomb = Nat1Bomb - (Bombloss // 5)
            displayloss1 = Bombloss // 5
            Bombloss2 = random.randint(1, max(1, Nat2Bomb // 5)) * 5
            Nat2Bomb = Nat2Bomb - (Bombloss2 // 5)
            displayloss2 = Bombloss2 // 5
            print("Nation 2 lost %s Bombers" % displayloss2)
            # gives a 6% casualty rate for the nation that rolled larger
            six_percent_loss = int(Nat2 * 0.06)
            Nat1 -= six_percent_loss
            # ends battle if aircraft are destroyed
            if Nat2 and Nat2Bomb <= 0:
                Nat2 = 0
                Nat2Bomb = 0
                print("nation 1 won the battle")
                break
        else:
            nat2_roll_wins += 1
            # subtract difference from the nations maximum if they rolled lower
            Nat1 -= difference
            # the twelve percent stored in new variable so it can be printed
            Bombloss1 = random.randint(1, max(1, Nat1Bomb // 5)) * 5
            Nat1Bomb = Nat1Bomb - (Bombloss1 // 5)
            displayloss1 = Bombloss1 // 5
            Bombloss2 = random.randint(1, max(1, Nat2Bomb // 5)) * 5
            Nat2Bomb = Nat2Bomb - (Bombloss2 // 5)
            displayloss2 = Bombloss2 // 5
            print(f"Nation 2 lost {displayloss2} Bombers")
            six_percent_loss = int(Nat1 * 0.06)
            Nat2 -= six_percent_loss

            print("Nation 1 lost %s Bombers" % displayloss1)
            # endsbattle if all are destroyed
            if Nat1 and Nat1Bomb <= 0:
                Nat1 = 0
                Nat1Bomb = 0
                print("nation 2 won the battle")
                break

        print("Battle difference: %s" % difference)
        print("6%% casualty value: %s" % six_percent_loss)

    if nat1_roll_wins > nat2_roll_wins:
        return f"{nat1_name} won the battle"
    return f"{nat2_name} won the battle"


if __name__ == "__main__":
    # Example invocation for local debugging
    ground_attack("Danzig", "Konigsburg", 630, 380, 4, 10)
