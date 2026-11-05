Feature: Driving a scene of bots
  As the offline eval substrate
  I want to drive bots turn-by-turn against each other and a synthetic player
  So that I can record reproducible transcripts the live game can never produce
  (in-game, bots cannot hear each other's words)

  Background:
    Given a fake brain
    And bots "Brumdar" and "Sylvara"

  Scenario: A player opener pulls bots into ordered chatter
    Given a synthetic player "Gus"
    When I run a 4-turn scene with seed 1
    Then the scene has 4 ordered non-empty turns
    And turn 0 is spoken by "Gus"
    And at least one bot has spoken

  Scenario: Scenes are reproducible for a given seed
    Given a synthetic player "Gus"
    When I run a 5-turn scene with seed 7
    And I run the scene again with the same seed
    Then both scenes have identical speakers and text

  Scenario: A scene with no player contains only bot speech
    Given no synthetic player
    When I run a 4-turn scene with seed 2
    Then every turn is spoken by a bot
    And "Gus" is not a participant

  Scenario: A player-less scene never calls chat (the brain requires a human name)
    Given no synthetic player
    When I run a 4-turn scene with seed 2
    Then the brain's chat endpoint was never called
