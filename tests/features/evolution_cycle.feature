Feature: One evolution optimizer cycle keeps or reverts a council edit
  As the evolution optimizer
  I want a candidate council edit kept only if it clears the margin, regresses nothing,
  introduces no guardrail failures, and the judge anchors haven't drifted
  So that the loop never promotes a degradation or fools itself

  Scenario: A clear win is kept and logged
    Given an evolution cycle with baseline eval mean 3.0 and candidate eval mean 3.8
    And held-out does not regress
    And no candidate guardrail failures
    And anchors are stable
    And the promotion margin is 0.5
    When the cycle runs
    Then the edit is KEPT
    And the cycle record is logged with kept true

  Scenario: A gain below the margin is reverted
    Given an evolution cycle with baseline eval mean 3.0 and candidate eval mean 3.3
    And held-out does not regress
    And no candidate guardrail failures
    And anchors are stable
    And the promotion margin is 0.5
    When the cycle runs
    Then the edit is REVERTED
    And the reasons include "eval gain <= margin"

  Scenario: A candidate that introduces a guardrail failure is reverted despite a higher score
    Given an evolution cycle with baseline eval mean 3.0 and candidate eval mean 4.5
    And held-out does not regress
    And the candidate has 1 guardrail failure
    And anchors are stable
    And the promotion margin is 0.5
    When the cycle runs
    Then the edit is REVERTED
    And the reasons include "new lore-gate failures"
