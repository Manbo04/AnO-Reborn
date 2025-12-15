import random


def ground_attack(
    nat1_name: str, nat2_name: str, nat1_soldiers: int, nat2_soldiers: int
) -> None:
    # TODO: get nation names from DB, get amount of soldiers from DB,
    # add tanks to script, add infra damage

    # print statements

    Nat1 = nat1_soldiers
    Nat2 = nat2_soldiers

    nat1_roll_wins = 0
    nat2_roll_wins = 0
    for _roll in range(0, 3):
        nat1_roll = random.randint(1, Nat1)
        nat2_roll = random.randint(1, Nat2)
        print(
            (
                "Soldier rolls: Nat1=%s (soldiers=%s), Nat2=%s (soldiers=%s)"
                % (nat1_roll, Nat1, nat2_roll, Nat2)
            )
        )
        # difference between the two rolls
        difference = abs(nat1_roll - nat2_roll)

        if nat1_roll > nat2_roll:
            nat1_roll_wins += 1
            # subtract difference from the nations maximum if they rolled lower
            Nat2 -= difference
            # gives a 12% casualty rate for the nation that rolled larger
            twelve_percent_loss = int(Nat2 * 0.12)
            Nat1 -= twelve_percent_loss
            print("Nation 2 casualties after battle: %s" % difference)
            print("Nation 1 casualties from battle: %s" % twelve_percent_loss)
        else:
            nat2_roll_wins += 1
            # subtract difference from the nations maximum if they rolled lower
            Nat1 -= difference
            # the twelve percent stored in new variable so it can be printed
            twelve_percent_loss = int(Nat1 * 0.12)
            Nat2 -= twelve_percent_loss
            print("Nation 1 casualties after battle: %s" % difference)
            print("Nation 2 casualties from battle: %s" % twelve_percent_loss)

    if nat1_roll_wins > nat2_roll_wins:
        print("Nation 1 won the battle")
    else:
        print("Nation 2 won the battle")


if __name__ == "__main__":
    # Example local invocation
    ground_attack("Blackadder", "CLRFL", 1500, 1500)
