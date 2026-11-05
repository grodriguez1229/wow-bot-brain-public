Feature: The promotion gate
  As the optimizer's safety core
  I want a candidate edit kept only if it clears noise, generalizes, stays in
  character, and does not coincide with judge drift
  So that unattended cycles cannot degrade the bots or fool themselves

  Background:
    Given a gate margin of 0.6

  Scenario: A clean win is kept
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 2.3
    And 0 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is keep

  Scenario: An eval gain within the margin is reverted
    Given baseline eval 2.0 and candidate eval 2.4
    And baseline held-out 2.0 and candidate held-out 2.3
    And 0 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "eval gain <= margin"

  Scenario: A held-out regression is reverted
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 1.9
    And 0 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "held-out regressed"

  Scenario: A new lore failure is reverted
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 2.3
    And 1 new lore failures
    And golden anchors at 3.0 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "new lore-gate failures"

  Scenario: Golden-anchor drift beyond the margin is reverted
    Given baseline eval 2.0 and candidate eval 2.8
    And baseline held-out 2.0 and candidate held-out 2.3
    And 0 new lore failures
    And golden anchors at 3.7 frozen 3.0
    When I evaluate the gate
    Then the decision is revert because "golden-anchor drift"
