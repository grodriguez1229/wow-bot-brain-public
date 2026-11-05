Feature: Scoring a scene transcript
  As the judge
  I want a per-dimension score with a hard lore/level gate
  So that a single gate violation can never be averaged away

  Scenario: A clean scene scores the mean of its five dimensions
    Given dimension scores intentions=4 turn_taking=4 continuity=3 initiative=3 voice=5
    And the gate passed
    When I compute the scene score
    Then the score is 3.8
    And the weakest dimension is "continuity"

  Scenario: A gate violation caps the score at 2.0
    Given dimension scores intentions=5 turn_taking=5 continuity=5 initiative=5 voice=5
    And the gate was violated with "flying mount in vanilla"
    When I compute the scene score
    Then the score is 2.0

  Scenario: A SceneScore round-trips through JSON
    Given a SceneScore for "s1" with score 3.8 and set version "v1"
    When I save and reload it
    Then the reloaded score has scene_id "s1" and set_version "v1"
