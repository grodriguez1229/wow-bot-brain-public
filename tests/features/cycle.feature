Feature: One optimize cycle (mechanical half)
  As the loop body
  I want to evaluate a candidate and finalize keep-or-revert
  So that the smart edit Claude made is gated and recorded deterministically

  Scenario: A winning candidate commits and advances baseline
    Given a candidate that scores eval 2.8 and held-out 2.3 with 0 new lore failures
    And the baseline is eval 2.0 held-out 2.0 and margin 0.6
    And golden anchors at 3.0 frozen 3.0
    When I finalize the cycle 1 "warmer chat prompt"
    Then the cycle is kept
    And git commit was called
    And the run log has 1 kept record

  Scenario: A losing candidate reverts and does not advance baseline
    Given a candidate that scores eval 2.3 and held-out 2.3 with 0 new lore failures
    And the baseline is eval 2.0 held-out 2.0 and margin 0.6
    And golden anchors at 3.0 frozen 3.0
    When I finalize the cycle 2 "shorter tick prompt"
    Then the cycle is reverted
    And git revert was called
    And the run log has 1 not-kept record
